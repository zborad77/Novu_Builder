import pytest

from app.core.config import Settings, get_settings
from app.main import initialize_job_queue

_STRONG_JWT = "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!"
_STRONG_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS = "a-strong-metrics-token-xyz-for-testing-123456789"
_STRONG_DB = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"
_STRONG_BASE_URL = "https://app.novu-builder.com"
_STRONG_CORS = "https://app.novu-builder.com"
_STRONG_S3_BUCKET = "my-production-bucket"
_STRONG_S3_REGION = "eu-central-1"


def _set_valid_prod_env(monkeypatch, **overrides):
    env = {
        "APP_ENV": "production",
        "JWT_SECRET": _STRONG_JWT,
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "7",
        "REDIS_URL": _STRONG_REDIS,
        "REDIS_FAILOVER_URLS": "",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "1.0",
        "REDIS_SOCKET_TIMEOUT": "1.0",
        "REDIS_HEALTH_CHECK_INTERVAL": "30",
        "REDIS_RETRY_ATTEMPTS": "3",
        "REDIS_RETRY_BACKOFF_BASE": "0.05",
        "REDIS_RETRY_BACKOFF_CAP": "0.5",
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "METRICS_AUTH_ENABLED": "true",
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
        "APP_BASE_URL": _STRONG_BASE_URL,
        "CORS_ALLOWED_ORIGINS": _STRONG_CORS,
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
        "S3_BUCKET": _STRONG_S3_BUCKET,
        "S3_REGION": _STRONG_S3_REGION,
        "S3_CONNECT_TIMEOUT_SECONDS": "3",
        "S3_READ_TIMEOUT_SECONDS": "10",
        "STORAGE_SIGNED_URL_TTL_SECONDS": "3600",
        "EXPORT_TTL_DAYS": "7",
    }
    env.update(overrides)
    for key, val in env.items():
        if val is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, val)


def test_get_settings_wraps_validation_errors_with_startup_prefix(monkeypatch):
    get_settings.cache_clear()
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_ENABLED="false")

    with pytest.raises(RuntimeError, match=r"^Startup validation failed \[config\]:"):
        get_settings()

    get_settings.cache_clear()


async def test_initialize_job_queue_uses_consistent_startup_prefix(monkeypatch):
    class FailingRedis:
        async def ping(self):
            raise RuntimeError("connection refused")

        async def aclose(self):
            return None

    _set_valid_prod_env(monkeypatch)
    settings = Settings()

    monkeypatch.setattr("app.main._build_redis_client", lambda _settings: FailingRedis())

    with pytest.raises(RuntimeError, match=r"^Startup validation failed \[redis\]:"):
        await initialize_job_queue(settings)
