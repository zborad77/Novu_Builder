"""Minimal Redis cache helpers (R-32).

Thin wrappers around redis.asyncio that:
  - fail open (no-op / cache miss) when redis is None or unavailable
  - namespace all keys under "cache:" to avoid collisions with the job queue
  - use JSON serialisation — callers control model_dump / model_validate

Typical call pattern (route handler):

    cached = await get_cached(redis, key)
    if cached is not None:
        return MyModel.model_validate(cached)

    result = await service.fetch(...)
    await set_cached(redis, key, result.model_dump(mode="json"), ttl=300)
    return result
"""
import json
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_PREFIX = "cache:"


def _k(key: str) -> str:
    return f"{_PREFIX}{key}"


async def get_cached(redis: Redis | None, key: str) -> Any | None:
    """Return the deserialised cached value, or None on miss / error."""
    if redis is None:
        return None
    try:
        raw = await redis.get(_k(key))
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("cache.get_error", key=key, error=str(exc))
        return None


async def set_cached(redis: Redis | None, key: str, value: Any, ttl: int) -> None:
    """Serialise `value` and store it with the given TTL (seconds). Fails silently."""
    if redis is None:
        return
    try:
        await redis.setex(_k(key), ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("cache.set_error", key=key, error=str(exc))


async def delete_cached(redis: Redis | None, *keys: str) -> None:
    """Delete one or more cache keys. Fails silently when Redis is unavailable."""
    if redis is None or not keys:
        return
    try:
        await redis.delete(*[_k(k) for k in keys])
    except Exception as exc:
        logger.warning("cache.delete_error", keys=keys, error=str(exc))
