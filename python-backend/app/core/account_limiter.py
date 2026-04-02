"""Per-account login brute-force protection (R-08).

Uses Redis as a shared counter store so throttling works correctly across
multiple application instances. When Redis is unavailable, falls back to an
in-memory counter so authentication-sensitive endpoints do not silently lose
their per-account protection during an outage.

Limits:
  _MAX_FAILED_ATTEMPTS consecutive failures within _WINDOW_SECONDS -> 429.
  Counter is cleared on any successful login.

Pass ``redis_client`` (the app's shared Redis instance from app.state.job_queue)
to reuse the existing connection pool instead of opening a new connection per
call. When ``redis_client`` is None the fallback creates a short-lived connection
from ``redis_url`` (original behaviour, preserves backward compatibility).
"""

import asyncio
import time

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.redis_client import build_redis_client_from_settings

logger = structlog.get_logger(__name__)

# 10 failed attempts within a 15-minute sliding window
_MAX_FAILED_ATTEMPTS: int = 10
_WINDOW_SECONDS: int = 900  # 15 minutes
_FALLBACK_FAILURES: dict[str, tuple[int, float]] = {}
_FALLBACK_LOCK = asyncio.Lock()


def _key(email: str) -> str:
    """Normalised Redis key for the per-account failure counter."""
    return f"auth:fail:{email.strip().lower()}"


def _email_domain(email: str) -> str:
    return email.strip().lower().split("@")[-1]


def _fallback_expired(expires_at: float, *, now: float | None = None) -> bool:
    return expires_at <= (time.monotonic() if now is None else now)


async def _fallback_is_account_throttled(email: str) -> bool:
    key = _key(email)
    now = time.monotonic()
    async with _FALLBACK_LOCK:
        state = _FALLBACK_FAILURES.get(key)
        if state is None:
            return False
        count, expires_at = state
        if _fallback_expired(expires_at, now=now):
            _FALLBACK_FAILURES.pop(key, None)
            return False
        return count >= _MAX_FAILED_ATTEMPTS


async def _fallback_record_login_failure(email: str) -> None:
    key = _key(email)
    now = time.monotonic()
    async with _FALLBACK_LOCK:
        count = 0
        state = _FALLBACK_FAILURES.get(key)
        if state is not None:
            prior_count, expires_at = state
            if not _fallback_expired(expires_at, now=now):
                count = prior_count
        _FALLBACK_FAILURES[key] = (count + 1, now + _WINDOW_SECONDS)


async def _fallback_reset_login_failures(email: str) -> None:
    async with _FALLBACK_LOCK:
        _FALLBACK_FAILURES.pop(_key(email), None)


def _log_fallback(email: str, *, operation: str, reason: str, error: str | None = None) -> None:
    logger.warning(
        "account_limiter.fallback_in_memory",
        operation=operation,
        email_domain=_email_domain(email),
        reason=reason,
        error=error,
    )


async def _get_client(redis_url: str) -> Redis | None:
    """Return a new short-lived Redis client, or None if Redis is unavailable."""
    try:
        client = build_redis_client_from_settings(
            get_settings(),
            redis_url=redis_url,
            client_name="novu-auth-limiter",
        )
        await client.ping()  # type: ignore[misc]  # redis.asyncio stubs: ping() typed as Awaitable|bool
        return client
    except Exception as exc:
        logger.debug("account_limiter.redis_unavailable", error=str(exc))
        return None


async def is_account_throttled(
    email: str,
    redis_url: str,
    *,
    redis_client: Redis | None = None,
) -> bool:
    """Return True when the account has exceeded the failed-attempt threshold."""
    owned = redis_client is None
    client = redis_client or await _get_client(redis_url)
    if client is None:
        _log_fallback(email, operation="check", reason="redis_unavailable")
        return await _fallback_is_account_throttled(email)
    try:
        raw = await client.get(_key(email))
        return raw is not None and int(raw) >= _MAX_FAILED_ATTEMPTS
    except Exception as exc:
        logger.error(
            "account_limiter.check_error",
            email_domain=_email_domain(email),
            error=str(exc),
        )
        _log_fallback(email, operation="check", reason="redis_error", error=str(exc))
        return await _fallback_is_account_throttled(email)
    finally:
        if owned and client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("account_limiter.close_error", error=str(exc))


async def record_login_failure(
    email: str,
    redis_url: str,
    *,
    redis_client: Redis | None = None,
) -> None:
    """Increment the failure counter and refresh the sliding TTL."""
    owned = redis_client is None
    client = redis_client or await _get_client(redis_url)
    if client is None:
        _log_fallback(email, operation="record", reason="redis_unavailable")
        await _fallback_record_login_failure(email)
        return
    try:
        key = _key(email)
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("account_limiter.record_error", email_domain=_email_domain(email), error=str(exc))
        _log_fallback(email, operation="record", reason="redis_error", error=str(exc))
        await _fallback_record_login_failure(email)
    finally:
        if owned:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("account_limiter.close_error", error=str(exc))


async def reset_login_failures(
    email: str,
    redis_url: str,
    *,
    redis_client: Redis | None = None,
) -> None:
    """Clear the failure counter after a successful login."""
    owned = redis_client is None
    client = redis_client or await _get_client(redis_url)
    if client is None:
        _log_fallback(email, operation="reset", reason="redis_unavailable")
        await _fallback_reset_login_failures(email)
        return
    try:
        await client.delete(_key(email))
    except Exception as exc:
        logger.warning("account_limiter.reset_error", email_domain=_email_domain(email), error=str(exc))
        _log_fallback(email, operation="reset", reason="redis_error", error=str(exc))
        await _fallback_reset_login_failures(email)
    finally:
        if owned:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("account_limiter.close_error", error=str(exc))
