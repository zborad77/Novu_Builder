from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from redis.retry import Retry

from app.core.config import Settings
from app.core.redis_client import (
    REDIS_HEALTH_CHECK_INTERVAL,
    REDIS_RETRY_ATTEMPTS,
    REDIS_RETRY_BACKOFF_BASE,
    REDIS_RETRY_BACKOFF_CAP,
    REDIS_SOCKET_CONNECT_TIMEOUT,
    REDIS_SOCKET_TIMEOUT,
    build_redis_client,
    build_redis_client_from_settings,
)
from app.main import _build_redis_client


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
        redis_socket_connect_timeout=2.0,
        redis_socket_timeout=3.0,
        redis_health_check_interval=20,
        redis_retry_attempts=4,
        redis_retry_backoff_base=0.1,
        redis_retry_backoff_cap=0.8,
    )

    with patch("app.main.build_redis_client_from_settings", return_value=object()) as build_client:
        _build_redis_client(settings)

    build_client.assert_called_once_with(
        settings,
        client_name="novu-backend",
    )


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
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!")
    monkeypatch.setenv("REDIS_URL", "redis://:a-strong-redis-password-xyz123@localhost:6379/0")
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_AUTH_TOKEN", "a-strong-metrics-token-xyz-for-testing-123456789")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod")
    monkeypatch.setenv("APP_BASE_URL", "https://app.novu-builder.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.novu-builder.com")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-production-bucket")
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(ValidationError, match=match):
        Settings()


def test_settings_reject_redis_backoff_cap_smaller_than_base(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!")
    monkeypatch.setenv("REDIS_URL", "redis://:a-strong-redis-password-xyz123@localhost:6379/0")
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_AUTH_TOKEN", "a-strong-metrics-token-xyz-for-testing-123456789")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod")
    monkeypatch.setenv("APP_BASE_URL", "https://app.novu-builder.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.novu-builder.com")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-production-bucket")
    monkeypatch.setenv("REDIS_RETRY_BACKOFF_BASE", str(REDIS_RETRY_BACKOFF_CAP))
    monkeypatch.setenv("REDIS_RETRY_BACKOFF_CAP", str(REDIS_RETRY_BACKOFF_BASE))

    with pytest.raises(ValidationError, match="REDIS_RETRY_BACKOFF_CAP must be >="):
        Settings()
