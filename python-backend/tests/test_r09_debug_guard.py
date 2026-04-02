"""R-09: APP_DEBUG default and production guard tests."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_JWT = "a-strong-secret-that-is-not-the-default-value-99!"
_STRONG_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS = "a-strong-metrics-token-xyz-for-testing-123456789"
_STRONG_DB = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"


def _set_valid_prod_runtime(monkeypatch) -> None:
    env = {
        "APP_ENV": "production",
        "REDIS_URL": _STRONG_REDIS,
        "REDIS_FAILOVER_URLS": "",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "1.0",
        "REDIS_SOCKET_TIMEOUT": "1.0",
        "REDIS_HEALTH_CHECK_INTERVAL": "30",
        "REDIS_RETRY_ATTEMPTS": "3",
        "REDIS_RETRY_BACKOFF_BASE": "0.05",
        "REDIS_RETRY_BACKOFF_CAP": "0.5",
        "METRICS_AUTH_ENABLED": "true",
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "WORKER_METRICS_ENABLED": "true",
        "WORKER_METRICS_HOST": "0.0.0.0",
        "WORKER_METRICS_PORT": "9101",
        "SENTRY_DSN": "",
        "SENTRY_TRACES_SAMPLE_RATE": "0.05",
        "SENTRY_PROFILES_SAMPLE_RATE": "0.0",
        "DATABASE_URL": _STRONG_DB,
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
        "ANALYSIS_JOB_MAX_ATTEMPTS": "3",
        "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS": "30",
        "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS": "300",
        "ANALYSIS_JOBS_PER_TENANT_LIMIT": "10",
        "WORKER_DB_POOL_SIZE": "0",
        "WORKER_DB_POOL_TIMEOUT": "30",
        "WORKER_INSTANCE_COUNT": "1",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "REQUIRE_HTTPS": "false",
        "HSTS_MAX_AGE": "31536000",
        "RATE_LIMIT_LOGIN": "5/minute",
        "RATE_LIMIT_ADMIN": "30/minute",
        "RATE_LIMIT_ADMIN_WRITE": "10/minute",
        "RATE_LIMIT_ADMIN_SENSITIVE": "5/minute",
        "RATE_LIMIT_UPLOAD": "30/minute",
        "RATE_LIMIT_ANALYSIS_JOBS": "20/minute",
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


def test_default_debug_is_false(monkeypatch):
    """APP_DEBUG field default is False (env file / env var may override in dev — here we test the field default directly)."""
    # Verify the model field default, not the runtime value loaded from .env
    field_default = Settings.model_fields["app_debug"].default
    assert field_default is False


def test_debug_allowed_in_development(monkeypatch):
    """APP_DEBUG=True is allowed in development."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_DEBUG", "true")
    s = Settings()
    assert s.app_debug is True


def test_debug_true_rejected_in_production(monkeypatch):
    """APP_DEBUG=True must raise ValidationError in production."""
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", _STRONG_JWT)
    with pytest.raises(ValidationError, match="APP_DEBUG=True is not allowed"):
        Settings()


def test_debug_false_allowed_in_production(monkeypatch):
    """APP_DEBUG=False (default) is allowed in production."""
    _set_valid_prod_runtime(monkeypatch)
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET", _STRONG_JWT)
    s = Settings()
    assert s.app_debug is False
