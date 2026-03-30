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


def _set_valid_prod_env(monkeypatch, **overrides):
    env = {
        "APP_ENV": "production",
        "JWT_SECRET": _STRONG_JWT,
        "REDIS_URL": _STRONG_REDIS,
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "METRICS_AUTH_ENABLED": "true",
        "DATABASE_URL": _STRONG_DB,
        "APP_BASE_URL": _STRONG_BASE_URL,
        "CORS_ALLOWED_ORIGINS": _STRONG_CORS,
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": _STRONG_S3_BUCKET,
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
