# =============================================================================
# JWT_SECRET startup guard tests
#
# Verify that Settings rejects the default JWT_SECRET in non-development
# environments and accepts it (or any custom value) in development.
# =============================================================================
import pytest
from pydantic import ValidationError

from app.core.config import Settings, _DEFAULT_JWT_SECRET

_CUSTOM_SECRET = "a-very-strong-and-unique-jwt-secret-for-testing-99!"
# Minimum valid production companions (satisfy all production validators)
_STRONG_REDIS_URL = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS_TOKEN = "a-strong-metrics-token-xyz-for-testing-123456789"
_STRONG_DB_URL = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"


def test_default_secret_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
    s = Settings()
    assert s.jwt_secret == _DEFAULT_JWT_SECRET


def test_default_secret_rejected_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
    with pytest.raises(ValidationError, match="JWT_SECRET must be changed"):
        Settings()


def test_default_secret_rejected_in_staging(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("JWT_SECRET", _DEFAULT_JWT_SECRET)
    with pytest.raises(ValidationError, match="JWT_SECRET must be changed"):
        Settings()


def test_custom_secret_allowed_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", _CUSTOM_SECRET)
    monkeypatch.setenv("REDIS_URL", _STRONG_REDIS_URL)
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_AUTH_TOKEN", _STRONG_METRICS_TOKEN)
    monkeypatch.setenv("DATABASE_URL", _STRONG_DB_URL)
    monkeypatch.setenv("APP_BASE_URL", "https://app.novu-builder.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.novu-builder.com")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-production-bucket")
    monkeypatch.setenv("S3_REGION", "eu-central-1")
    s = Settings()
    assert s.jwt_secret == _CUSTOM_SECRET


def test_placeholder_secret_rejected_in_production(monkeypatch):
    """JWT_SECRET containing 'CHANGE_ME' (e.g. from .env.production template) must be rejected."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "CHANGE_ME_USE_A_STRONG_RANDOM_SECRET")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings()


def test_short_secret_rejected_in_production(monkeypatch):
    """JWT_SECRET shorter than 32 chars must be rejected in production."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "tooshort")
    monkeypatch.setenv("REDIS_URL", _STRONG_REDIS_URL)
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.setenv("METRICS_AUTH_TOKEN", _STRONG_METRICS_TOKEN)
    monkeypatch.setenv("DATABASE_URL", _STRONG_DB_URL)
    monkeypatch.setenv("APP_BASE_URL", "https://app.novu-builder.com")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.novu-builder.com")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-production-bucket")
    monkeypatch.setenv("S3_REGION", "eu-central-1")
    with pytest.raises(ValidationError, match="too short"):
        Settings()
