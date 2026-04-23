"""Shared Redis client defaults for backend and worker paths.

The worker can override ``socket_timeout`` because blocking queue operations
intentionally wait, but connect timeout and idle-socket health checks should
stay consistent.

This module now also provides a conservative failover-ready wrapper for the
shared queue/runtime Redis client:

- multiple candidate Redis URLs can be configured
- startup succeeds when any candidate is reachable
- read-style commands may fail over and retry once on the next candidate
- write-style commands never retry transparently after a transport failure,
  because enqueue/dequeue/lease scripts must remain truthful and auditable
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any, AsyncIterator
from urllib.parse import SplitResult, urlsplit, urlunsplit

from redis.asyncio import Redis
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError, TimeoutError as RedisTimeoutError
from redis.retry import Retry

logger = logging.getLogger(__name__)

REDIS_SOCKET_CONNECT_TIMEOUT = 1.0
REDIS_SOCKET_TIMEOUT = 1.0
REDIS_HEALTH_CHECK_INTERVAL = 30
REDIS_RETRY_ATTEMPTS = 3
REDIS_RETRY_BACKOFF_BASE = 0.05
REDIS_RETRY_BACKOFF_CAP = 0.5

_USE_SETTINGS_SOCKET_TIMEOUT = object()


class RedisFailoverWriteError(RuntimeError):
    """A mutating Redis command failed and failover state changed.

    The caller must treat the original operation as unknown / not acknowledged
    and decide explicitly whether a higher-level retry is safe.
    """

    def __init__(
        self,
        *,
        operation: str,
        failed_url: str,
        active_url: str | None,
        cause: Exception,
    ) -> None:
        active_suffix = f"; active failover target={active_url}" if active_url else ""
        super().__init__(
            f"Redis write operation '{operation}' failed on {failed_url}{active_suffix}. "
            "Operation was not retried automatically."
        )
        self.operation = operation
        self.failed_url = failed_url
        self.active_url = active_url
        self.cause = cause


@dataclass(frozen=True)
class RedisRuntimeStatus:
    mode: str
    state: str
    candidate_count: int
    active_url: str | None
    degraded: bool
    last_error: str | None
    last_failover_at: str | None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.password is None:
        return url
    username = parts.username or ""
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port is not None else ""
    userinfo = f"{username}:***" if username else ":***"
    netloc = f"{userinfo}@{host}{port}"
    sanitized = SplitResult(parts.scheme, netloc, parts.path, parts.query, parts.fragment)
    return urlunsplit(sanitized)


def build_redis_retry(
    *,
    retry_attempts: int = REDIS_RETRY_ATTEMPTS,
    retry_backoff_base: float = REDIS_RETRY_BACKOFF_BASE,
    retry_backoff_cap: float = REDIS_RETRY_BACKOFF_CAP,
) -> Retry:
    return Retry(
        ExponentialBackoff(
            base=retry_backoff_base,
            cap=retry_backoff_cap,
        ),
        retry_attempts,
    )


def build_redis_client(
    redis_url: str,
    *,
    socket_connect_timeout: float = REDIS_SOCKET_CONNECT_TIMEOUT,
    socket_timeout: float | None = REDIS_SOCKET_TIMEOUT,
    health_check_interval: int = REDIS_HEALTH_CHECK_INTERVAL,
    retry_attempts: int = REDIS_RETRY_ATTEMPTS,
    retry_backoff_base: float = REDIS_RETRY_BACKOFF_BASE,
    retry_backoff_cap: float = REDIS_RETRY_BACKOFF_CAP,
    client_name: str | None = None,
) -> Redis:
    return Redis.from_url(
        redis_url,
        socket_connect_timeout=socket_connect_timeout,
        socket_timeout=socket_timeout,
        health_check_interval=health_check_interval,
        retry=build_redis_retry(
            retry_attempts=retry_attempts,
            retry_backoff_base=retry_backoff_base,
            retry_backoff_cap=retry_backoff_cap,
        ),
        retry_on_timeout=retry_attempts > 0,
        client_name=client_name,
    )


def build_redis_client_from_settings(
    settings: Any,
    *,
    redis_url: str | None = None,
    socket_timeout: float | None | object = _USE_SETTINGS_SOCKET_TIMEOUT,
    client_name: str | None = None,
) -> Redis:
    resolved_socket_timeout = (
        settings.redis_socket_timeout
        if socket_timeout is _USE_SETTINGS_SOCKET_TIMEOUT
        else socket_timeout
    )
    return build_redis_client(
        redis_url or settings.redis_url,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_timeout=resolved_socket_timeout,
        health_check_interval=settings.redis_health_check_interval,
        retry_attempts=settings.redis_retry_attempts,
        retry_backoff_base=settings.redis_retry_backoff_base,
        retry_backoff_cap=settings.redis_retry_backoff_cap,
        client_name=client_name,
    )


def parse_failover_redis_urls(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (tuple, list)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


class FailoverRedisClient:
    """A conservative multi-endpoint Redis wrapper.

    Truthfulness rules:
    - reads may fail over and retry once on the next candidate
    - writes may switch the active candidate after a transport failure, but the
      original write is not replayed automatically
    """

    def __init__(
        self,
        *,
        urls: tuple[str, ...],
        clients: tuple[Redis, ...],
    ) -> None:
        if not urls or len(urls) != len(clients):
            raise ValueError("FailoverRedisClient requires matching Redis URLs and clients.")
        self._urls = urls
        self._clients = clients
        self._active_index = 0
        self._degraded = False
        self._last_error: str | None = None
        self._last_failover_at: str | None = None

    @property
    def active_url(self) -> str:
        return self._urls[self._active_index]

    @property
    def candidate_count(self) -> int:
        return len(self._urls)

    def runtime_status(self) -> RedisRuntimeStatus:
        mode = "failover" if self.candidate_count > 1 else "single"
        state = "degraded" if self._degraded else "ready"
        return RedisRuntimeStatus(
            mode=mode,
            state=state,
            candidate_count=self.candidate_count,
            active_url=_redact_url(self.active_url),
            degraded=self._degraded,
            last_error=self._last_error,
            last_failover_at=self._last_failover_at,
        )

    async def aclose(self) -> None:
        for client in self._clients:
            try:
                await client.aclose()
            except Exception:
                continue

    def pipeline(self):
        return self._clients[self._active_index].pipeline()

    async def ping(self):
        return await self._run_read("ping")

    async def rpush(self, *args, **kwargs):
        return await self._run_write("rpush", *args, **kwargs)

    async def lpush(self, *args, **kwargs):
        return await self._run_write("lpush", *args, **kwargs)

    async def llen(self, *args, **kwargs):
        return await self._run_read("llen", *args, **kwargs)

    async def lrange(self, *args, **kwargs):
        return await self._run_read("lrange", *args, **kwargs)

    async def lindex(self, *args, **kwargs):
        return await self._run_read("lindex", *args, **kwargs)

    async def lrem(self, *args, **kwargs):
        return await self._run_write("lrem", *args, **kwargs)

    async def eval(self, *args, **kwargs):
        return await self._run_write("eval", *args, **kwargs)

    async def zrange(self, *args, **kwargs):
        return await self._run_read("zrange", *args, **kwargs)

    async def zrangebyscore(self, *args, **kwargs):
        return await self._run_read("zrangebyscore", *args, **kwargs)

    async def zcard(self, *args, **kwargs):
        return await self._run_read("zcard", *args, **kwargs)

    async def zcount(self, *args, **kwargs):
        return await self._run_read("zcount", *args, **kwargs)

    async def zrem(self, *args, **kwargs):
        return await self._run_write("zrem", *args, **kwargs)

    async def hgetall(self, *args, **kwargs):
        return await self._run_read("hgetall", *args, **kwargs)

    async def hmget(self, *args, **kwargs):
        return await self._run_read("hmget", *args, **kwargs)

    async def get(self, *args, **kwargs):
        return await self._run_read("get", *args, **kwargs)

    async def mget(self, *args, **kwargs):
        return await self._run_read("mget", *args, **kwargs)

    async def delete(self, *args, **kwargs):
        return await self._run_write("delete", *args, **kwargs)

    async def set(self, *args, **kwargs):
        return await self._run_write("set", *args, **kwargs)

    async def srem(self, *args, **kwargs):
        return await self._run_write("srem", *args, **kwargs)

    async def smembers(self, *args, **kwargs):
        return await self._run_read("smembers", *args, **kwargs)

    async def sismember(self, *args, **kwargs):
        return await self._run_read("sismember", *args, **kwargs)

    async def scard(self, *args, **kwargs):
        return await self._run_read("scard", *args, **kwargs)

    async def scan_iter(self, *args, **kwargs) -> AsyncIterator[object]:
        client = await self._get_active_client()
        try:
            async for item in client.scan_iter(*args, **kwargs):
                yield item
            return
        except Exception as exc:
            if not self._is_transport_error(exc):
                raise
            switched = await self._promote_next_available(failed_index=self._active_index, cause=exc)
            if switched is None:
                raise
            client = self._clients[switched]
            async for item in client.scan_iter(*args, **kwargs):
                yield item

    async def _run_read(self, operation: str, *args, **kwargs):
        client = await self._get_active_client()
        try:
            return await getattr(client, operation)(*args, **kwargs)
        except Exception as exc:
            if not self._is_transport_error(exc):
                raise
            switched = await self._promote_next_available(failed_index=self._active_index, cause=exc)
            if switched is None:
                raise
            return await getattr(self._clients[switched], operation)(*args, **kwargs)

    async def _run_write(self, operation: str, *args, **kwargs):
        client = await self._get_active_client()
        failed_url = _redact_url(self.active_url)
        try:
            return await getattr(client, operation)(*args, **kwargs)
        except Exception as exc:
            if not self._is_transport_error(exc):
                raise
            switched = await self._promote_next_available(failed_index=self._active_index, cause=exc)
            active_url = _redact_url(self._urls[switched]) if switched is not None else None
            raise RedisFailoverWriteError(
                operation=operation,
                failed_url=failed_url,
                active_url=active_url,
                cause=exc,
            ) from exc

    async def _get_active_client(self) -> Redis:
        return self._clients[self._active_index]

    async def _promote_next_available(self, *, failed_index: int, cause: Exception) -> int | None:
        self._last_error = str(cause)
        if self.candidate_count == 1:
            return None

        for offset in range(1, self.candidate_count):
            candidate_index = (failed_index + offset) % self.candidate_count
            candidate = self._clients[candidate_index]
            try:
                await candidate.ping()
            except Exception as candidate_exc:
                if not self._is_transport_error(candidate_exc):
                    continue
                self._last_error = str(candidate_exc)
                continue

            self._active_index = candidate_index
            self._degraded = True
            self._last_failover_at = _utc_now_iso()
            logger.warning(
                "redis.failover_activated",
                extra={
                    "failed_url": _redact_url(self._urls[failed_index]),
                    "active_url": _redact_url(self._urls[candidate_index]),
                    "candidate_count": self.candidate_count,
                    "error": str(cause),
                },
            )
            return candidate_index
        return None

    @staticmethod
    def _is_transport_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                OSError,
                ConnectionError,
                TimeoutError,
                RedisConnectionError,
                RedisTimeoutError,
            ),
        ) or isinstance(exc, RedisError) and "connection" in str(exc).lower()


def build_queue_redis_client_from_settings(
    settings: Any,
    *,
    redis_url: str | None = None,
    socket_timeout: float | None | object = _USE_SETTINGS_SOCKET_TIMEOUT,
    client_name: str | None = None,
) -> FailoverRedisClient:
    primary_url = redis_url or settings.redis_url
    failover_urls = parse_failover_redis_urls(getattr(settings, "redis_failover_urls", ""))
    candidate_urls = tuple(dict.fromkeys((primary_url, *failover_urls)))
    clients = tuple(
        build_redis_client_from_settings(
            settings,
            redis_url=url,
            socket_timeout=socket_timeout,
            client_name=client_name,
        )
        for url in candidate_urls
    )
    return FailoverRedisClient(
        urls=candidate_urls,
        clients=clients,
    )
