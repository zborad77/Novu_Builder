"""Per-account login brute-force protection (R-08).

Uses Redis as a shared counter store so throttling works correctly across
multiple application instances. Fails open (no throttling) when Redis is
unavailable — the existing per-IP slowapi limit remains the last-resort guard.

Limits:
  _MAX_FAILED_ATTEMPTS consecutive failures within _WINDOW_SECONDS → 429.
  Counter is cleared on any successful login.
"""
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

# 10 failed attempts within a 15-minute sliding window
_MAX_FAILED_ATTEMPTS: int = 10
_WINDOW_SECONDS: int = 900  # 15 minutes

# Fail-fast connect timeout — don't block the login path if Redis is slow
_REDIS_TIMEOUT: float = 1.0


def _key(email: str) -> str:
    """Normalised Redis key for the per-account failure counter."""
    return f"auth:fail:{email.strip().lower()}"


async def _get_client(redis_url: str) -> Redis | None:
    """Return a connected Redis client, or None if Redis is unavailable."""
    try:
        client = Redis.from_url(
            redis_url,
            socket_connect_timeout=_REDIS_TIMEOUT,
            socket_timeout=_REDIS_TIMEOUT,
        )
        await client.ping()  # type: ignore[misc]  # redis.asyncio stubs: ping() typed as Awaitable|bool
        return client
    except Exception as exc:
        logger.debug("account_limiter.redis_unavailable", error=str(exc))
        return None


async def is_account_throttled(email: str, redis_url: str) -> bool:
    """Return True when the account has exceeded the failed-attempt threshold."""
    client = await _get_client(redis_url)
    if client is None:
        return False  # fail open — per-IP limit still applies
    try:
        raw = await client.get(_key(email))
        return raw is not None and int(raw) >= _MAX_FAILED_ATTEMPTS
    except Exception:
        logger.warning("account_limiter.check_error", email_domain=email.split("@")[-1])
        return False
    finally:
        await client.aclose()


async def record_login_failure(email: str, redis_url: str) -> None:
    """Increment the failure counter and refresh the sliding TTL."""
    client = await _get_client(redis_url)
    if client is None:
        return
    try:
        key = _key(email)
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS)
        await pipe.execute()
    except Exception:
        logger.warning("account_limiter.record_error", email_domain=email.split("@")[-1])
    finally:
        await client.aclose()


async def reset_login_failures(email: str, redis_url: str) -> None:
    """Clear the failure counter after a successful login."""
    client = await _get_client(redis_url)
    if client is None:
        return
    try:
        await client.delete(_key(email))
    except Exception:
        logger.warning("account_limiter.reset_error", email_domain=email.split("@")[-1])
    finally:
        await client.aclose()
