# =============================================================================
# Production startup hardening tests
#
# Verify that Settings raises ValidationError for missing or placeholder
# values of METRICS_AUTH_TOKEN, REDIS_URL, DATABASE_URL and STORAGE_BACKEND
# in production, and that dev / test environments remain tolerant.
# =============================================================================
import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_JWT = "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!"
_STRONG_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS = "a-strong-metrics-token-xyz-for-testing-123456789"
_STRONG_DB = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"
_STRONG_BASE_URL = "https://app.example.com"
_STRONG_S3_BUCKET = "my-production-bucket"


def _set_valid_prod_env(monkeypatch, **overrides):
    """Set the minimum set of env vars that satisfy all production validators."""
    env = {
        "APP_ENV": "production",
        "JWT_SECRET": _STRONG_JWT,
        "REDIS_URL": _STRONG_REDIS,
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "METRICS_AUTH_ENABLED": "true",
        "DATABASE_URL": _STRONG_DB,
        "APP_BASE_URL": _STRONG_BASE_URL,
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": _STRONG_S3_BUCKET,
    }
    env.update(overrides)
    for key, val in env.items():
        if val is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, val)


# ── METRICS_AUTH_TOKEN ────────────────────────────────────────────────────────

def test_metrics_token_required_in_production_when_enabled(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv("METRICS_AUTH_TOKEN", raising=False)
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN must be set"):
        Settings()


def test_metrics_token_placeholder_rejected_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="change-me")
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN contains an insecure placeholder"):
        Settings()


def test_metrics_token_changeme_variant_rejected(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="CHANGE_ME_TOKEN_HERE")
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN"):
        Settings()


def test_metrics_token_not_required_when_guard_disabled(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_ENABLED="false")
    monkeypatch.delenv("METRICS_AUTH_TOKEN", raising=False)
    s = Settings()
    assert s.metrics_auth_token is None


def test_metrics_token_not_required_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "true")
    monkeypatch.delenv("METRICS_AUTH_TOKEN", raising=False)
    s = Settings()
    assert s.metrics_auth_token is None


# ── REDIS_URL password ────────────────────────────────────────────────────────

def test_redis_no_password_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://localhost:6379/0")
    with pytest.raises(ValidationError, match="REDIS_URL must include a password"):
        Settings()


def test_redis_placeholder_password_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://:change-me@localhost:6379/0")
    with pytest.raises(ValidationError, match="insecure placeholder password"):
        Settings()


def test_redis_changeme_variant_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://:changeme@localhost:6379/0")
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings()


def test_redis_strong_password_passes_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    s = Settings()
    assert "redis://" in s.redis_url


def test_redis_no_password_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    s = Settings()
    assert s.redis_url == "redis://localhost:6379/0"


# ── DATABASE_URL placeholder password ────────────────────────────────────────

def test_database_placeholder_password_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://novu:change-me@localhost:5432/novu_prod")
    with pytest.raises(ValidationError, match="DATABASE_URL contains an insecure placeholder password"):
        Settings()


def test_database_changeme_variant_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://novu:CHANGE_ME@localhost:5432/novu_prod")
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings()


def test_database_strong_password_passes_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    s = Settings()
    assert "novu_prod" in s.database_url


def test_database_no_password_url_passes_in_production(monkeypatch):
    """Trust-auth or cert-auth PostgreSQL URLs with no password must not be rejected."""
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://novu@localhost:5432/novu_prod")
    s = Settings()
    assert s.database_url.startswith("postgresql")


def test_database_placeholder_allowed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://novu:change-me@localhost:5432/novu_dev")
    s = Settings()
    assert "novu_dev" in s.database_url


# ── STORAGE_BACKEND ───────────────────────────────────────────────────────────

def test_storage_local_fails_in_production(monkeypatch):
    """STORAGE_BACKEND='local' must be rejected in production."""
    _set_valid_prod_env(monkeypatch, STORAGE_BACKEND="local", S3_BUCKET=None)
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings()


def test_storage_unknown_backend_fails_in_production(monkeypatch):
    """Any unrecognised STORAGE_BACKEND value is rejected in production (not silently local)."""
    _set_valid_prod_env(monkeypatch, STORAGE_BACKEND="blob", S3_BUCKET=None)
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings()


def test_storage_s3_without_bucket_fails_in_production(monkeypatch):
    """STORAGE_BACKEND='s3' without S3_BUCKET must be rejected in production."""
    _set_valid_prod_env(monkeypatch, STORAGE_BACKEND="s3", S3_BUCKET="")
    with pytest.raises(ValidationError, match="S3_BUCKET must be set"):
        Settings()


def test_storage_s3_with_bucket_passes_in_production(monkeypatch):
    """STORAGE_BACKEND='s3' with a non-empty S3_BUCKET is valid in production."""
    _set_valid_prod_env(monkeypatch)
    s = Settings()
    assert s.storage_backend == "s3"
    assert s.s3_bucket == _STRONG_S3_BUCKET


def test_storage_local_allowed_in_development(monkeypatch):
    """STORAGE_BACKEND='local' must be allowed in development."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    s = Settings()
    assert s.storage_backend == "local"


def test_storage_local_allowed_in_test(monkeypatch):
    """STORAGE_BACKEND='local' must be allowed in test."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    s = Settings()
    assert s.storage_backend == "local"


def test_storage_local_fails_in_staging(monkeypatch):
    """STORAGE_BACKEND='local' must also be rejected in staging (not only 'production')."""
    _set_valid_prod_env(monkeypatch, APP_ENV="staging", STORAGE_BACKEND="local", S3_BUCKET=None)
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings()


# ── APP_BASE_URL ──────────────────────────────────────────────────────────────

def test_app_base_url_localhost_fails_in_production(monkeypatch):
    """APP_BASE_URL pointing to localhost must be rejected in production."""
    _set_valid_prod_env(monkeypatch, APP_BASE_URL="http://localhost:8000")
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()


def test_app_base_url_127_fails_in_production(monkeypatch):
    """APP_BASE_URL pointing to 127.0.0.1 must be rejected in production."""
    _set_valid_prod_env(monkeypatch, APP_BASE_URL="http://127.0.0.1:8000")
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()


def test_app_base_url_empty_fails_in_production(monkeypatch):
    """Empty APP_BASE_URL must be rejected in production."""
    _set_valid_prod_env(monkeypatch, APP_BASE_URL="")
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()


def test_app_base_url_valid_passes_in_production(monkeypatch):
    """A valid https APP_BASE_URL must be accepted in production."""
    _set_valid_prod_env(monkeypatch)
    s = Settings()
    assert s.app_base_url == _STRONG_BASE_URL


def test_app_base_url_localhost_fails_in_staging(monkeypatch):
    """APP_BASE_URL pointing to localhost must also be rejected in staging."""
    _set_valid_prod_env(monkeypatch, APP_ENV="staging", APP_BASE_URL="http://localhost:8000")
    with pytest.raises(ValidationError, match="APP_BASE_URL"):
        Settings()


def test_app_base_url_localhost_allowed_in_development(monkeypatch):
    """localhost APP_BASE_URL must be tolerated in development (warning only)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
    s = Settings()
    assert "localhost" in s.app_base_url


def test_app_base_url_localhost_allowed_in_test(monkeypatch):
    """localhost APP_BASE_URL must be tolerated in test environment."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:8000")
    s = Settings()
    assert "localhost" in s.app_base_url
