from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from redis.retry import Retry

from app.core.config import Settings
from app.core.redis_client import (
    FailoverRedisClient,
    REDIS_HEALTH_CHECK_INTERVAL,
    REDIS_RETRY_ATTEMPTS,
    REDIS_RETRY_BACKOFF_BASE,
    REDIS_RETRY_BACKOFF_CAP,
    REDIS_SOCKET_CONNECT_TIMEOUT,
    REDIS_SOCKET_TIMEOUT,
    RedisFailoverWriteError,
    build_redis_client,
    build_redis_client_from_settings,
    build_queue_redis_client_from_settings,
)
from app.main import _build_redis_client


def _set_valid_prod_runtime(monkeypatch) -> None:
    env = {
        "APP_ENV": "production",
        "JWT_SECRET": "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "REDIS_URL": "redis://:a-strong-redis-password-xyz123@localhost:6379/0",
        "REDIS_FAILOVER_URLS": "",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "1.0",
        "REDIS_SOCKET_TIMEOUT": "1.0",
        "REDIS_HEALTH_CHECK_INTERVAL": "30",
        "REDIS_RETRY_ATTEMPTS": "3",
        "REDIS_RETRY_BACKOFF_BASE": "0.05",
        "REDIS_RETRY_BACKOFF_CAP": "0.5",
        "METRICS_AUTH_ENABLED": "true",
        "METRICS_AUTH_TOKEN": "a-strong-metrics-token-xyz-for-testing-123456789",
        "WORKER_METRICS_ENABLED": "true",
        "WORKER_METRICS_HOST": "0.0.0.0",
        "WORKER_METRICS_PORT": "9101",
        "SENTRY_DSN": "",
        "SENTRY_TRACES_SAMPLE_RATE": "0.05",
        "SENTRY_PROFILES_SAMPLE_RATE": "0.0",
        "DATABASE_URL": "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod",
        "DB_POOL_SIZE": "10",
        "DB_MAX_OVERFLOW": "10",
        "DB_POOL_TIMEOUT": "30",
        "DB_POOL_RECYCLE": "1800",
        "APP_BASE_URL": "https://app.novu-builder.com",
        "CORS_ALLOWED_ORIGINS": "https://app.novu-builder.com",
        "AI_ANALYSIS_PROVIDER": "mock",
        "WORKER_CONCURRENCY": "2",
        "WORKER_HEAVY_CONCURRENCY": "1",
        "WORKER_JOB_LEASE_TIMEOUT_SECONDS": "600",
        "WORKER_HEAVY_JOB_LEASE_TIMEOUT_SECONDS": "1800",
        "WORKER_JOB_REAP_INTERVAL_SECONDS": "30",
        "WORKER_HEAVY_JOB_REAP_INTERVAL_SECONDS": "30",
        "READINESS_PROCESSING_GRACE_SECONDS": "75",
        "ANALYSIS_QUEUE_MAX_DEPTH": "100",
        "HEAVY_QUEUE_MAX_DEPTH": "50",
        "BACKPRESSURE_MAX_CONCURRENT_JOBS": "0",
        "BACKPRESSURE_MAX_QUEUED_JOBS": "0",
        "BACKPRESSURE_MAX_RETRY_INFLIGHT": "0",
        "ANALYSIS_JOB_MAX_ATTEMPTS": "3",
        "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS": "30",
        "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS": "300",
        "ANALYSIS_JOBS_PER_TENANT_LIMIT": "10",
        "WORKER_DB_POOL_SIZE": "0",
        "WORKER_DB_POOL_TIMEOUT": "30",
        "WORKER_INSTANCE_COUNT": "1",
        "REQUIRE_HTTPS": "false",
        "HSTS_MAX_AGE": "31536000",
        "RATE_LIMIT_LOGIN": "5/minute",
        "RATE_LIMIT_ADMIN": "30/minute",
        "RATE_LIMIT_ADMIN_WRITE": "10/minute",
        "RATE_LIMIT_ADMIN_SENSITIVE": "5/minute",
        "RATE_LIMIT_UPLOAD": "30/minute",
        "RATE_LIMIT_ANALYSIS_JOBS": "20/minute",
        "RATE_LIMIT_READ_LIST": "120/minute",
        "RATE_LIMIT_READ_DETAIL": "60/minute",
        "STORAGE_BACKEND": "s3",
        "STORAGE_AUTHORITATIVE": "true",
        "S3_BUCKET": "my-production-bucket",
        "S3_REGION": "eu-central-1",
        "S3_CONNECT_TIMEOUT_SECONDS": "3",
        "S3_READ_TIMEOUT_SECONDS": "10",
        "STORAGE_SIGNED_URL_TTL_SECONDS": "3600",
        "EXPORT_TTL_DAYS": "7",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_build_redis_client_uses_hardened_defaults():
    with patch("app.core.redis_client.Redis.from_url", return_value=object()) as from_url:
        build_redis_client("redis://:secret@localhost:6379/0")

    from_url.assert_called_once_with(
        "redis://:secret@localhost:6379/0",
        socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
        health_check_interval=REDIS_HEALTH_CHECK_INTERVAL,
        retry_on_timeout=True,
        retry=from_url.call_args.kwargs["retry"],
        client_name=None,
    )
    retry = from_url.call_args.kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry._retries == REDIS_RETRY_ATTEMPTS  # noqa: SLF001 - introspecting configured retry budget


def test_build_redis_client_accepts_explicit_retry_and_timeout_overrides():
    with patch("app.core.redis_client.Redis.from_url", return_value=object()) as from_url:
        build_redis_client(
            "redis://:secret@localhost:6379/0",
            socket_connect_timeout=2.5,
            socket_timeout=4.0,
            health_check_interval=45,
            retry_attempts=5,
            retry_backoff_base=0.1,
            retry_backoff_cap=1.0,
            client_name="custom-client",
        )

    kwargs = from_url.call_args.kwargs
    assert kwargs["socket_connect_timeout"] == 2.5
    assert kwargs["socket_timeout"] == 4.0
    assert kwargs["health_check_interval"] == 45
    assert kwargs["retry_on_timeout"] is True
    assert kwargs["client_name"] == "custom-client"
    retry = kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry._retries == 5  # noqa: SLF001 - configuration assertion


def test_backend_job_queue_uses_shared_redis_builder():
    settings = SimpleNamespace(
        redis_url="redis://:secret@localhost:6379/0",
        redis_failover_urls="",
        redis_socket_connect_timeout=2.0,
        redis_socket_timeout=3.0,
        redis_health_check_interval=20,
        redis_retry_attempts=4,
        redis_retry_backoff_base=0.1,
        redis_retry_backoff_cap=0.8,
    )

    with patch("app.main.build_queue_redis_client_from_settings", return_value=object()) as build_client:
        _build_redis_client(settings)

    build_client.assert_called_once_with(
        settings,
        client_name="novu-backend",
    )


def test_build_queue_redis_client_from_settings_wraps_primary_and_failover_candidates():
    settings = SimpleNamespace(
        redis_url="redis://:secret@primary:6379/0",
        redis_failover_urls="redis://:secret@replica-a:6379/0, redis://:secret@replica-b:6379/0",
        redis_socket_connect_timeout=1.5,
        redis_socket_timeout=2.5,
        redis_health_check_interval=25,
        redis_retry_attempts=6,
        redis_retry_backoff_base=0.2,
        redis_retry_backoff_cap=0.9,
    )

    with patch(
        "app.core.redis_client.build_redis_client_from_settings",
        side_effect=[object(), object(), object()],
    ) as build_client:
        client = build_queue_redis_client_from_settings(settings, client_name="novu-test")

    assert isinstance(client, FailoverRedisClient)
    assert client.candidate_count == 3
    assert build_client.call_count == 3


@pytest.mark.asyncio
async def test_failover_client_ping_promotes_second_candidate_when_primary_down():
    primary = AsyncMock()
    primary.ping = AsyncMock(side_effect=OSError("primary down"))
    secondary = AsyncMock()
    secondary.ping = AsyncMock(return_value=True)

    client = FailoverRedisClient(
        urls=(
            "redis://:secret@primary:6379/0",
            "redis://:secret@secondary:6379/0",
        ),
        clients=(primary, secondary),
    )

    assert await client.ping() is True
    status = client.runtime_status()
    assert status.state == "degraded"
    assert status.candidate_count == 2
    assert "secondary" in (status.active_url or "")


@pytest.mark.asyncio
async def test_failover_client_retries_reads_on_next_candidate():
    primary = AsyncMock()
    primary.llen = AsyncMock(side_effect=OSError("primary down"))
    secondary = AsyncMock()
    secondary.ping = AsyncMock(return_value=True)
    secondary.llen = AsyncMock(return_value=7)

    client = FailoverRedisClient(
        urls=(
            "redis://:secret@primary:6379/0",
            "redis://:secret@secondary:6379/0",
        ),
        clients=(primary, secondary),
    )

    assert await client.llen("analysis:jobs") == 7
    assert client.runtime_status().state == "degraded"
    secondary.llen.assert_awaited_once_with("analysis:jobs")


@pytest.mark.asyncio
async def test_failover_client_does_not_retry_mutating_commands_after_transport_failure():
    primary = AsyncMock()
    primary.eval = AsyncMock(side_effect=OSError("primary down"))
    secondary = AsyncMock()
    secondary.ping = AsyncMock(return_value=True)
    secondary.eval = AsyncMock(return_value=1)
    secondary.llen = AsyncMock(return_value=3)

    client = FailoverRedisClient(
        urls=(
            "redis://:secret@primary:6379/0",
            "redis://:secret@secondary:6379/0",
        ),
        clients=(primary, secondary),
    )

    with pytest.raises(RedisFailoverWriteError, match="Operation was not retried automatically"):
        await client.eval("return 1", 0)

    secondary.eval.assert_not_awaited()
    assert await client.llen("analysis:jobs") == 3
    assert client.runtime_status().state == "degraded"


def test_build_redis_client_from_settings_uses_settings_values():
    settings = SimpleNamespace(
        redis_url="redis://:secret@localhost:6379/0",
        redis_socket_connect_timeout=1.5,
        redis_socket_timeout=2.5,
        redis_health_check_interval=25,
        redis_retry_attempts=6,
        redis_retry_backoff_base=0.2,
        redis_retry_backoff_cap=0.9,
    )

    with patch("app.core.redis_client.Redis.from_url", return_value=object()) as from_url:
        build_redis_client_from_settings(settings, client_name="novu-test")

    kwargs = from_url.call_args.kwargs
    assert kwargs["socket_connect_timeout"] == 1.5
    assert kwargs["socket_timeout"] == 2.5
    assert kwargs["health_check_interval"] == 25
    assert kwargs["client_name"] == "novu-test"
    retry = kwargs["retry"]
    assert isinstance(retry, Retry)
    assert retry._retries == 6  # noqa: SLF001 - configuration assertion


def test_build_redis_client_from_settings_allows_worker_socket_timeout_override():
    settings = SimpleNamespace(
        redis_url="redis://:secret@localhost:6379/0",
        redis_socket_connect_timeout=1.5,
        redis_socket_timeout=2.5,
        redis_health_check_interval=25,
        redis_retry_attempts=6,
        redis_retry_backoff_base=0.2,
        redis_retry_backoff_cap=0.9,
    )

    with patch("app.core.redis_client.Redis.from_url", return_value=object()) as from_url:
        build_redis_client_from_settings(
            settings,
            socket_timeout=None,
            client_name="novu-worker",
        )

    assert from_url.call_args.kwargs["socket_timeout"] is None


@pytest.mark.parametrize(
    ("env_name", "env_value", "match"),
    [
        ("REDIS_SOCKET_CONNECT_TIMEOUT", "0", "REDIS_SOCKET_CONNECT_TIMEOUT"),
        ("REDIS_SOCKET_TIMEOUT", "0", "REDIS_SOCKET_TIMEOUT"),
        ("REDIS_HEALTH_CHECK_INTERVAL", "-1", "REDIS_HEALTH_CHECK_INTERVAL"),
        ("REDIS_RETRY_ATTEMPTS", "-1", "REDIS_RETRY_ATTEMPTS"),
        ("REDIS_RETRY_BACKOFF_BASE", "0", "REDIS_RETRY_BACKOFF_BASE"),
        ("REDIS_RETRY_BACKOFF_CAP", "0", "REDIS_RETRY_BACKOFF_CAP"),
    ],
)
def test_settings_reject_invalid_redis_tuning(monkeypatch, env_name, env_value, match):
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(ValidationError, match=match):
        Settings()


def test_settings_reject_redis_backoff_cap_smaller_than_base(monkeypatch):
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv("REDIS_RETRY_BACKOFF_BASE", str(REDIS_RETRY_BACKOFF_CAP))
    monkeypatch.setenv("REDIS_RETRY_BACKOFF_CAP", str(REDIS_RETRY_BACKOFF_BASE))

    with pytest.raises(ValidationError, match="REDIS_RETRY_BACKOFF_CAP must be >="):
        Settings()


def test_settings_reject_duplicate_failover_redis_candidates(monkeypatch):
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://:a-strong-redis-password-xyz123@primary:6379/0")
    monkeypatch.setenv("REDIS_FAILOVER_URLS", "redis://:a-strong-redis-password-xyz123@primary:6379/0")

    with pytest.raises(ValidationError, match="Failover endpoints must be explicit and unique"):
        Settings()


def test_settings_reject_invalid_failover_redis_candidate(monkeypatch):
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://:a-strong-redis-password-xyz123@primary:6379/0")
    monkeypatch.setenv("REDIS_FAILOVER_URLS", "http://bad-host:6379/0")

    with pytest.raises(ValidationError, match="REDIS_FAILOVER_URLS\\[1\\] must use redis:// or rediss://"):
        Settings()
