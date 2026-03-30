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
_STRONG_BASE_URL = "https://app.novu-builder.com"
_STRONG_CORS = "https://app.novu-builder.com"
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


# ── METRICS_AUTH_TOKEN ────────────────────────────────────────────────────────

def test_metrics_token_required_in_production_when_enabled(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv("METRICS_AUTH_TOKEN", raising=False)
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN must be set"):
        Settings()


def test_metrics_auth_cannot_be_disabled_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_ENABLED="false")
    with pytest.raises(ValidationError, match="METRICS_AUTH_ENABLED must remain true"):
        Settings()


def test_metrics_token_placeholder_rejected_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="change-me")
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN contains an insecure placeholder"):
        Settings()


def test_metrics_token_changeme_variant_rejected(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="CHANGE_ME_TOKEN_HERE")
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN"):
        Settings()


def test_metrics_token_template_placeholder_rejected(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="<generated-token>")
    with pytest.raises(ValidationError, match="METRICS_AUTH_TOKEN contains an insecure placeholder"):
        Settings()


def test_metrics_token_too_short_rejected_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, METRICS_AUTH_TOKEN="short-token")
    with pytest.raises(ValidationError, match="too short"):
        Settings()


def test_metrics_token_not_required_when_guard_disabled_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("METRICS_AUTH_ENABLED", "false")
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


def test_redis_empty_password_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://:@localhost:6379/0")
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


def test_redis_invalid_scheme_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="http://:a-strong-redis-password-xyz123@localhost:6379/0")
    with pytest.raises(ValidationError, match="REDIS_URL must use redis:// or rediss://"):
        Settings()


def test_redis_missing_host_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://:a-strong-redis-password-xyz123@:6379/0")
    with pytest.raises(ValidationError, match="REDIS_URL must include a Redis host"):
        Settings()


def test_redis_short_password_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="redis://:shortpassword@localhost:6379/0")
    with pytest.raises(ValidationError, match="REDIS_URL password is too short"):
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


def test_redis_empty_url_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, REDIS_URL="")
    with pytest.raises(ValidationError, match="REDIS_URL must be set"):
        Settings()


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


def test_database_sqlite_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="sqlite+aiosqlite:///./python-backend.db")
    with pytest.raises(ValidationError, match="must not use SQLite"):
        Settings()


def test_database_requires_async_driver_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod")
    with pytest.raises(ValidationError, match="DATABASE_URL must use a PostgreSQL async driver"):
        Settings()


def test_database_requires_host_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@:5432/novu_prod")
    with pytest.raises(ValidationError, match="DATABASE_URL must include a database host"):
        Settings()


def test_database_requires_name_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, DATABASE_URL="postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost")
    with pytest.raises(ValidationError, match="DATABASE_URL must include a database name"):
        Settings()


def test_database_sync_sqlite_override_fails_in_production(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        DATABASE_URL_SYNC="sqlite:///./python-backend.db",
    )
    with pytest.raises(ValidationError, match="DATABASE_URL_SYNC must not use SQLite"):
        Settings()


def test_database_sync_override_async_driver_fails_in_production(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        DATABASE_URL_SYNC="postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod",
    )
    with pytest.raises(ValidationError, match="DATABASE_URL_SYNC must use a PostgreSQL sync driver"):
        Settings()


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


def test_storage_unknown_backend_fails_in_development(monkeypatch):
    """Unknown STORAGE_BACKEND values must not silently fall back to local disk."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STORAGE_BACKEND", "blob")
    with pytest.raises(ValidationError, match="not supported"):
        Settings()


def test_storage_local_fails_in_staging(monkeypatch):
    """STORAGE_BACKEND='local' must also be rejected in staging (not only 'production')."""
    _set_valid_prod_env(monkeypatch, APP_ENV="staging", STORAGE_BACKEND="local", S3_BUCKET=None)
    with pytest.raises(ValidationError, match="STORAGE_BACKEND"):
        Settings()


def test_storage_placeholder_bucket_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_BUCKET="change-me-bucket")
    with pytest.raises(ValidationError, match="S3_BUCKET looks like an unfilled placeholder"):
        Settings()


def test_storage_partial_s3_credentials_fail(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_ACCESS_KEY_ID="AKIA123456789", S3_SECRET_ACCESS_KEY="")
    with pytest.raises(ValidationError, match="must be set together"):
        Settings()


def test_storage_placeholder_s3_secret_fails(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        S3_ACCESS_KEY_ID="AKIA123456789",
        S3_SECRET_ACCESS_KEY="change-me",
    )
    with pytest.raises(ValidationError, match="S3_SECRET_ACCESS_KEY"):
        Settings()


def test_storage_placeholder_cdn_url_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_CDN_BASE_URL="https://cdn.example.com")
    with pytest.raises(ValidationError, match="S3_CDN_BASE_URL looks like an unfilled placeholder"):
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


def test_app_base_url_placeholder_domain_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, APP_BASE_URL="https://app.yourdomain.com")
    with pytest.raises(ValidationError, match="looks like an example/template placeholder"):
        Settings()


def test_app_base_url_invalid_url_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, APP_BASE_URL="app.novu-builder.com")
    with pytest.raises(ValidationError, match="APP_BASE_URL must be a valid http\\(s\\) URL"):
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


# ── CORS_ALLOWED_ORIGINS ──────────────────────────────────────────────────────

def test_cors_localhost_only_fails_in_production(monkeypatch):
    """CORS_ALLOWED_ORIGINS with only localhost must be rejected in production."""
    _set_valid_prod_env(monkeypatch, CORS_ALLOWED_ORIGINS="http://localhost:8000")
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS contains only localhost"):
        Settings()


def test_cors_127_only_fails_in_production(monkeypatch):
    """CORS_ALLOWED_ORIGINS with only 127.0.0.1 must be rejected in production."""
    _set_valid_prod_env(monkeypatch, CORS_ALLOWED_ORIGINS="http://127.0.0.1:8000,http://127.0.0.1:3000")
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
        Settings()


def test_cors_placeholder_origin_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://app.example.com")
    with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS contains placeholder/example origin"):
        Settings()


def test_cors_mixed_origins_pass_in_production(monkeypatch):
    """CORS_ALLOWED_ORIGINS with at least one non-localhost origin passes in production."""
    _set_valid_prod_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://app.novu-builder.com,http://localhost:3000")
    s = Settings()
    assert "app.novu-builder.com" in s.cors_allowed_origins


def test_cors_real_origin_passes_in_production(monkeypatch):
    """A real production CORS origin must be accepted."""
    _set_valid_prod_env(monkeypatch, CORS_ALLOWED_ORIGINS="https://app.novu-builder.com")
    s = Settings()
    assert s.cors_allowed_origins == "https://app.novu-builder.com"


def test_cors_localhost_allowed_in_development(monkeypatch):
    """localhost CORS origins must be tolerated in development."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000")
    s = Settings()
    assert "localhost" in s.cors_allowed_origins


def test_cors_localhost_allowed_in_test(monkeypatch):
    """localhost CORS origins must be tolerated in test environment."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    s = Settings()
    assert "localhost" in s.cors_allowed_origins
