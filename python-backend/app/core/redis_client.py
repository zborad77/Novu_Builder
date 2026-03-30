"""Shared Redis client defaults for backend and worker paths.

The worker can override ``socket_timeout`` because BLPOP intentionally blocks,
but connect timeout and idle-socket health checks should stay consistent.
"""
from typing import Any

from redis.backoff import ExponentialBackoff
from redis.retry import Retry
from redis.asyncio import Redis

REDIS_SOCKET_CONNECT_TIMEOUT = 1.0
REDIS_SOCKET_TIMEOUT = 1.0
REDIS_HEALTH_CHECK_INTERVAL = 30
REDIS_RETRY_ATTEMPTS = 3
REDIS_RETRY_BACKOFF_BASE = 0.05
REDIS_RETRY_BACKOFF_CAP = 0.5

_USE_SETTINGS_SOCKET_TIMEOUT = object()


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
