"""Per-account login brute-force protection (R-08).

Uses Redis as the only shared counter store so throttling remains truthful
across multiple application instances. Security-sensitive auth flows must not
silently degrade to a pod-local fallback when the shared backend is
unavailable.

Limits:
  _MAX_FAILED_ATTEMPTS consecutive failures within _WINDOW_SECONDS -> 429.
  Counter is cleared on any successful login.

Pass ``redis_client`` (the app's shared Redis instance from app.state.job_queue)
to reuse the existing connection pool instead of opening a new connection per
call. When ``redis_client`` is None a short-lived client is created from
``redis_url``.
"""

from __future__ import annotations

import structlog
from redis.asyncio import Redis
from typing import NoReturn

from app.core.config import get_settings
from app.core.redis_client import build_redis_client_from_settings

logger = structlog.get_logger(__name__)

# 10 failed attempts within a 15-minute sliding window
_MAX_FAILED_ATTEMPTS: int = 10
_WINDOW_SECONDS: int = 900  # 15 minutes


class AccountThrottleBackendUnavailableError(RuntimeError):
    """Raised when the shared auth throttle backend cannot be used truthfully."""

    def __init__(
        self,
        *,
        operation: str,
        email: str,
        cause: Exception,
    ) -> None:
        self.operation = operation
        self.email_domain = _email_domain(email)
        self.cause = cause
        super().__init__(
            f"Shared auth throttle backend is unavailable during {operation} for {self.email_domain!r}."
        )


def _key(email: str) -> str:
    """Normalised Redis key for the per-account failure counter."""
    return f"auth:fail:{email.strip().lower()}"


def _email_domain(email: str) -> str:
    return email.strip().lower().split("@")[-1]


def _raise_backend_unavailable(
    *,
    operation: str,
    email: str,
    error: Exception,
) -> NoReturn:
    logger.error(
        "account_limiter.backend_unavailable",
        operation=operation,
        email_domain=_email_domain(email),
        error=str(error),
    )
    raise AccountThrottleBackendUnavailableError(
        operation=operation,
        email=email,
        cause=error,
    ) from error


def _can_retry_without_shared_client(error: Exception) -> bool:
    message = str(error).lower()
    return "different loop" in message or "event loop is closed" in message


async def _get_client(redis_url: str) -> Redis:
    """Return a new short-lived Redis client, or raise when Redis is unavailable."""
    client = build_redis_client_from_settings(
        get_settings(),
        redis_url=redis_url,
        client_name="novu-auth-limiter",
    )
    try:
        await client.ping()  # type: ignore[misc]  # redis.asyncio stubs: ping() typed as Awaitable|bool
        return client
    except Exception:
        try:
            await client.aclose()
        except Exception as close_exc:
            logger.warning("account_limiter.close_error", error=str(close_exc))
        raise


async def is_account_throttled(
    email: str,
    redis_url: str,
    *,
    redis_client: Redis | None = None,
) -> bool:
    """Return True when the account has exceeded the failed-attempt threshold."""
    owned = redis_client is None
    client: Redis | None = None
    try:
        client = redis_client or await _get_client(redis_url)
        raw = await client.get(_key(email))
        return raw is not None and int(raw) >= _MAX_FAILED_ATTEMPTS
    except Exception as exc:
        if redis_client is not None and _can_retry_without_shared_client(exc):
            logger.warning(
                "account_limiter.shared_client_unusable",
                operation="check",
                email_domain=_email_domain(email),
                error=str(exc),
            )
            return await is_account_throttled(email, redis_url, redis_client=None)
        _raise_backend_unavailable(operation="check", email=email, error=exc)
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
    client: Redis | None = None
    try:
        client = redis_client or await _get_client(redis_url)
        key = _key(email)
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS)
        await pipe.execute()
    except Exception as exc:
        if redis_client is not None and _can_retry_without_shared_client(exc):
            logger.warning(
                "account_limiter.shared_client_unusable",
                operation="record",
                email_domain=_email_domain(email),
                error=str(exc),
            )
            await record_login_failure(email, redis_url, redis_client=None)
            return
        _raise_backend_unavailable(operation="record", email=email, error=exc)
    finally:
        if owned and client is not None:
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
    client: Redis | None = None
    try:
        client = redis_client or await _get_client(redis_url)
        await client.delete(_key(email))
    except Exception as exc:
        if redis_client is not None and _can_retry_without_shared_client(exc):
            logger.warning(
                "account_limiter.shared_client_unusable",
                operation="reset",
                email_domain=_email_domain(email),
                error=str(exc),
            )
            await reset_login_failures(email, redis_url, redis_client=None)
            return
        _raise_backend_unavailable(operation="reset", email=email, error=exc)
    finally:
        if owned and client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("account_limiter.close_error", error=str(exc))
