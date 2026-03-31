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
from time import perf_counter
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.metrics import observe_cache_operation

logger = structlog.get_logger(__name__)

_PREFIX = "cache:"


def _k(key: str) -> str:
    return f"{_PREFIX}{key}"


def _namespace(key: str) -> str:
    head = key.split(":", 1)[0].strip().lower()
    return head or "default"


async def get_cached(redis: Redis | None, key: str) -> Any | None:
    """Return the deserialised cached value, or None on miss / error."""
    namespace = _namespace(key)
    started_at = perf_counter()
    if redis is None:
        observe_cache_operation(
            namespace=namespace,
            operation="get",
            outcome="unavailable",
            duration_seconds=perf_counter() - started_at,
        )
        return None
    try:
        raw = await redis.get(_k(key))
        outcome = "hit" if raw is not None else "miss"
        observe_cache_operation(
            namespace=namespace,
            operation="get",
            outcome=outcome,
            duration_seconds=perf_counter() - started_at,
        )
        return json.loads(raw) if raw is not None else None
    except Exception as exc:
        logger.warning("cache.get_error", key=key, error=str(exc))
        observe_cache_operation(
            namespace=namespace,
            operation="get",
            outcome="error",
            duration_seconds=perf_counter() - started_at,
        )
        return None


async def set_cached(redis: Redis | None, key: str, value: Any, ttl: int) -> None:
    """Serialise `value` and store it with the given TTL (seconds). Fails silently."""
    namespace = _namespace(key)
    started_at = perf_counter()
    if redis is None:
        observe_cache_operation(
            namespace=namespace,
            operation="set",
            outcome="unavailable",
            duration_seconds=perf_counter() - started_at,
        )
        return
    try:
        await redis.setex(_k(key), ttl, json.dumps(value, default=str))
        observe_cache_operation(
            namespace=namespace,
            operation="set",
            outcome="success",
            duration_seconds=perf_counter() - started_at,
        )
    except Exception as exc:
        logger.warning("cache.set_error", key=key, error=str(exc))
        observe_cache_operation(
            namespace=namespace,
            operation="set",
            outcome="error",
            duration_seconds=perf_counter() - started_at,
        )


async def delete_cached(redis: Redis | None, *keys: str) -> None:
    """Delete one or more cache keys. Fails silently when Redis is unavailable."""
    if not keys:
        return
    namespace = _namespace(keys[0])
    started_at = perf_counter()
    if redis is None:
        observe_cache_operation(
            namespace=namespace,
            operation="delete",
            outcome="unavailable",
            duration_seconds=perf_counter() - started_at,
        )
        return
    try:
        await redis.delete(*[_k(k) for k in keys])
        observe_cache_operation(
            namespace=namespace,
            operation="delete",
            outcome="success",
            duration_seconds=perf_counter() - started_at,
        )
    except Exception as exc:
        logger.warning("cache.delete_error", keys=keys, error=str(exc))
        observe_cache_operation(
            namespace=namespace,
            operation="delete",
            outcome="error",
            duration_seconds=perf_counter() - started_at,
        )
