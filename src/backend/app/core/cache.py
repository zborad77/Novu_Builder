"""Strict cache helpers.

Cache is an optimization only. The database remains authoritative.

Every Redis cache entry is wrapped in a versioned envelope and must have:
  - a positive TTL at write time
  - an explicit tag/version provided by the caller

Stale, malformed, or untagged cache entries are treated as misses and never
served as truth.
"""
import json
from dataclasses import dataclass
from time import monotonic, perf_counter
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.metrics import observe_cache_operation
from app.core.tenant_timing import (
    CACHE_ACCESS_TIMING_FLOOR_SECONDS,
    enforce_timing_floor,
)

logger = structlog.get_logger(__name__)

_PREFIX = "cache:"
_TAG_PREFIX = "cache-tag:"
_CACHE_ENVELOPE_VERSION = 1
_DEFAULT_TAG_VALUE = "0"
_TAG_TTL_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class _LocalCacheEntry:
    value: Any
    tag: str
    expires_at_monotonic: float


class VersionTaggedLocalCache:
    def __init__(self, *, namespace: str, ttl_seconds: int):
        ttl = int(ttl_seconds)
        if ttl <= 0:
            raise ValueError("Local cache TTL must be positive.")
        self.namespace = namespace
        self.ttl_seconds = ttl
        self._entries: dict[Any, _LocalCacheEntry] = {}

    def get(self, key: Any, *, tag: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            observe_cache_operation(namespace=self.namespace, operation="local_get", outcome="miss")
            return None
        if monotonic() >= entry.expires_at_monotonic:
            self._entries.pop(key, None)
            observe_cache_operation(namespace=self.namespace, operation="local_get", outcome="expired")
            return None
        if entry.tag != str(tag):
            self._entries.pop(key, None)
            observe_cache_operation(namespace=self.namespace, operation="local_get", outcome="stale")
            return None
        observe_cache_operation(namespace=self.namespace, operation="local_get", outcome="hit")
        return entry.value

    def set(self, key: Any, value: Any, *, tag: str) -> None:
        self._entries[key] = _LocalCacheEntry(
            value=value,
            tag=str(tag),
            expires_at_monotonic=monotonic() + self.ttl_seconds,
        )
        observe_cache_operation(namespace=self.namespace, operation="local_set", outcome="success")

    def invalidate(self, key: Any | None = None) -> None:
        if key is None:
            self._entries.clear()
            return
        self._entries.pop(key, None)

    def invalidate_where(self, predicate) -> None:
        stale_keys = [cache_key for cache_key in self._entries if predicate(cache_key)]
        for cache_key in stale_keys:
            self._entries.pop(cache_key, None)


def _k(key: str) -> str:
    return f"{_PREFIX}{key}"


def _tag_key(scope: str) -> str:
    return f"{_TAG_PREFIX}{scope}"


def _namespace(key: str) -> str:
    head = key.split(":", 1)[0].strip().lower()
    return head or "default"


def _normalize_tag(tag: str | int) -> str:
    normalized = str(tag).strip()
    if not normalized:
        raise ValueError("Cache tag must be a non-empty string.")
    return normalized


def _build_envelope(*, value: Any, ttl: int, tag: str) -> dict[str, Any]:
    return {
        "meta": {
            "version": _CACHE_ENVELOPE_VERSION,
            "tag": _normalize_tag(tag),
            "ttlSeconds": int(ttl),
        },
        "value": value,
    }


def _decode_envelope(raw: object) -> tuple[str, Any] | None:
    if raw is None:
        return None
    decoded = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    if int(meta.get("version", 0) or 0) != _CACHE_ENVELOPE_VERSION:
        return None
    tag = meta.get("tag")
    ttl_seconds = meta.get("ttlSeconds")
    if not isinstance(tag, str) or not tag.strip():
        return None
    if ttl_seconds is None:
        return None
    try:
        if int(ttl_seconds) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    if "value" not in payload:
        return None
    return tag, payload["value"]


async def get_cache_tag(redis: Redis | None, scope: str) -> str:
    if redis is None:
        return _DEFAULT_TAG_VALUE
    try:
        raw = await redis.get(_tag_key(scope))
    except Exception as exc:
        logger.warning("cache.tag_get_error", scope=scope, error=str(exc))
        return _DEFAULT_TAG_VALUE
    if raw is None:
        return _DEFAULT_TAG_VALUE
    decoded = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
    return decoded.strip() or _DEFAULT_TAG_VALUE


async def invalidate_cache_tag(redis: Redis | None, scope: str) -> str:
    if redis is None:
        return _DEFAULT_TAG_VALUE
    try:
        next_value = await redis.incr(_tag_key(scope))
        await redis.expire(_tag_key(scope), _TAG_TTL_SECONDS)
    except Exception as exc:
        logger.warning("cache.tag_invalidate_error", scope=scope, error=str(exc))
        return _DEFAULT_TAG_VALUE
    return str(int(next_value))


async def get_cached(redis: Redis | None, key: str, *, tag: str) -> Any | None:
    """Return the cached value only when the entry envelope matches the current tag."""
    namespace = _namespace(key)
    started_at = perf_counter()
    expected_tag = _normalize_tag(tag)
    try:
        if redis is None:
            observe_cache_operation(
                namespace=namespace,
                operation="get",
                outcome="unavailable",
                duration_seconds=perf_counter() - started_at,
            )
            return None
        raw = await redis.get(_k(key))
        envelope = _decode_envelope(raw)
        outcome = "miss"
        if envelope is not None:
            cached_tag, cached_value = envelope
            if cached_tag == expected_tag:
                outcome = "hit"
                observe_cache_operation(
                    namespace=namespace,
                    operation="get",
                    outcome=outcome,
                    duration_seconds=perf_counter() - started_at,
                )
                return cached_value
            outcome = "stale"
            try:
                await redis.delete(_k(key))
            except Exception:
                pass
        observe_cache_operation(
            namespace=namespace,
            operation="get",
            outcome=outcome,
            duration_seconds=perf_counter() - started_at,
        )
        return None
    except Exception as exc:
        logger.warning("cache.get_error", key=key, error=str(exc))
        observe_cache_operation(
            namespace=namespace,
            operation="get",
            outcome="error",
            duration_seconds=perf_counter() - started_at,
        )
        return None
    finally:
        await enforce_timing_floor(
            started_at,
            minimum_seconds=CACHE_ACCESS_TIMING_FLOOR_SECONDS,
        )


async def set_cached(redis: Redis | None, key: str, value: Any, ttl: int, *, tag: str) -> None:
    """Serialise `value` and store it with the given TTL and explicit tag."""
    namespace = _namespace(key)
    started_at = perf_counter()
    ttl_seconds = int(ttl)
    if ttl_seconds <= 0:
        raise ValueError("Cache TTL must be positive.")
    envelope = _build_envelope(value=value, ttl=ttl_seconds, tag=tag)
    if redis is None:
        observe_cache_operation(
            namespace=namespace,
            operation="set",
            outcome="unavailable",
            duration_seconds=perf_counter() - started_at,
        )
        return
    try:
        await redis.setex(_k(key), ttl_seconds, json.dumps(envelope, default=str))
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
