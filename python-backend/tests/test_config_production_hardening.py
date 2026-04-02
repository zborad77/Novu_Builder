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
_STRONG_S3_REGION = "eu-central-1"


def _set_valid_prod_env(monkeypatch, **overrides):
    """Set the minimum set of env vars that satisfy all production validators."""
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


def test_worker_metrics_cannot_be_disabled_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, WORKER_METRICS_ENABLED="false")
    with pytest.raises(ValidationError, match="WORKER_METRICS_ENABLED must remain true"):
        Settings()


def test_strict_runtime_profile_requires_explicit_worker_concurrency(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv("WORKER_CONCURRENCY", raising=False)
    with pytest.raises(ValidationError, match="WORKER_CONCURRENCY"):
        Settings()


def test_strict_runtime_profile_requires_explicit_sentry_state(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    with pytest.raises(ValidationError, match="SENTRY_DSN"):
        Settings()


def test_sentry_dsn_placeholder_rejected_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/1")
    with pytest.raises(ValidationError, match="SENTRY_DSN looks like an unfilled placeholder"):
        Settings()


# -- AI_ANALYSIS_PROVIDER ----------------------------------------------------

def test_openai_provider_blocked_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, AI_ANALYSIS_PROVIDER="openai")
    with pytest.raises(ValidationError, match="OpenAI vision provider is not implemented"):
        Settings()


def test_openai_provider_blocked_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_ANALYSIS_PROVIDER", "openai")
    with pytest.raises(ValidationError, match="OpenAI vision provider is not implemented"):
        Settings()


def test_unknown_provider_rejected_even_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_ANALYSIS_PROVIDER", "mystery")
    with pytest.raises(ValidationError, match="AI_ANALYSIS_PROVIDER"):
        Settings()


def test_claude_provider_requires_api_key_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, AI_ANALYSIS_PROVIDER="claude", ANTHROPIC_API_KEY=None)
    with pytest.raises(ValidationError, match="requires ANTHROPIC_API_KEY"):
        Settings()


def test_claude_provider_requires_non_placeholder_api_key(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        AI_ANALYSIS_PROVIDER="claude",
        ANTHROPIC_API_KEY="change-me",
    )
    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY looks like an unfilled placeholder"):
        Settings()


def test_claude_provider_with_api_key_passes_in_production(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        AI_ANALYSIS_PROVIDER="CLAUDE",
        ANTHROPIC_API_KEY="sk-ant-realistic-test-key-1234567890",
    )
    s = Settings()
    assert s.ai_analysis_provider == "claude"


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


def test_invalid_rate_limit_format_fails_fast(monkeypatch):
    _set_valid_prod_env(monkeypatch, RATE_LIMIT_LOGIN="burst-mode")
    with pytest.raises(ValidationError, match="RATE_LIMIT_LOGIN must use '<count>/<window>' format"):
        Settings()


def test_reap_interval_must_stay_below_lease_timeout(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        WORKER_JOB_LEASE_TIMEOUT_SECONDS="60",
        WORKER_JOB_REAP_INTERVAL_SECONDS="60",
    )
    with pytest.raises(ValidationError, match="WORKER_JOB_REAP_INTERVAL_SECONDS must be < WORKER_JOB_LEASE_TIMEOUT_SECONDS"):
        Settings()


def test_tenant_job_limit_cannot_exceed_queue_depth(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        ANALYSIS_QUEUE_MAX_DEPTH="5",
        ANALYSIS_JOBS_PER_TENANT_LIMIT="6",
    )
    with pytest.raises(ValidationError, match="ANALYSIS_JOBS_PER_TENANT_LIMIT must be <= ANALYSIS_QUEUE_MAX_DEPTH"):
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
    _set_valid_prod_env(
        monkeypatch,
        STORAGE_BACKEND="local",
        STORAGE_AUTHORITATIVE="false",
        S3_BUCKET=None,
    )
    with pytest.raises(ValidationError, match="Local storage is not allowed in production"):
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
    assert s.storage_authoritative is True


def test_storage_s3_without_region_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_REGION=None)
    with pytest.raises(ValidationError, match="S3_REGION must be set"):
        Settings()


def test_storage_authoritative_false_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, STORAGE_AUTHORITATIVE="false")
    with pytest.raises(ValidationError, match="STORAGE_AUTHORITATIVE must remain true"):
        Settings()


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
    _set_valid_prod_env(
        monkeypatch,
        APP_ENV="staging",
        STORAGE_BACKEND="local",
        STORAGE_AUTHORITATIVE="false",
        S3_BUCKET=None,
    )
    with pytest.raises(ValidationError, match="Local storage is not allowed in production"):
        Settings()


def test_storage_production_guard(monkeypatch):
    """Production must fail fast when STORAGE_BACKEND falls back to local."""
    _set_valid_prod_env(
        monkeypatch,
        STORAGE_BACKEND="local",
        STORAGE_AUTHORITATIVE="false",
        S3_BUCKET=None,
    )
    with pytest.raises(ValidationError, match="Local storage is not allowed in production"):
        Settings()


def test_storage_placeholder_bucket_fails_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_BUCKET="change-me-bucket")
    with pytest.raises(ValidationError, match="S3_BUCKET looks like an unfilled placeholder"):
        Settings()


def test_storage_partial_s3_credentials_fail(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_ACCESS_KEY_ID="AKIA123456789", S3_SECRET_ACCESS_KEY="")
    with pytest.raises(ValidationError, match="must be set together"):
        Settings()


def test_storage_placeholder_s3_access_key_fails(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        S3_ACCESS_KEY_ID="change-me-access-key",
        S3_SECRET_ACCESS_KEY="a-real-secret-key-for-tests",
    )
    with pytest.raises(ValidationError, match="S3_ACCESS_KEY_ID"):
        Settings()


def test_storage_placeholder_s3_secret_fails(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        S3_ACCESS_KEY_ID="AKIA123456789",
        S3_SECRET_ACCESS_KEY="change-me",
    )
    with pytest.raises(ValidationError, match="S3_SECRET_ACCESS_KEY"):
        Settings()


def test_storage_cdn_url_rejected_with_signed_url_policy(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_CDN_BASE_URL="https://cdn.example.com")
    with pytest.raises(ValidationError, match="S3_CDN_BASE_URL is not supported with signed URL policy"):
        Settings()


def test_storage_signed_url_ttl_above_max_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, STORAGE_SIGNED_URL_TTL_SECONDS="3601")
    with pytest.raises(ValidationError, match="STORAGE_SIGNED_URL_TTL_SECONDS must be between 1 and 3600"):
        Settings()


def test_s3_connect_timeout_zero_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_CONNECT_TIMEOUT_SECONDS="0")
    with pytest.raises(ValidationError, match="S3_CONNECT_TIMEOUT_SECONDS must be > 0"):
        Settings()


def test_s3_read_timeout_zero_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, S3_READ_TIMEOUT_SECONDS="0")
    with pytest.raises(ValidationError, match="S3_READ_TIMEOUT_SECONDS must be > 0"):
        Settings()


def test_s3_timeouts_valid_pass(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        S3_CONNECT_TIMEOUT_SECONDS="2.5",
        S3_READ_TIMEOUT_SECONDS="8.0",
    )
    settings = Settings()
    assert settings.s3_connect_timeout_seconds == 2.5
    assert settings.s3_read_timeout_seconds == 8.0


def test_storage_signed_url_ttl_zero_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, STORAGE_SIGNED_URL_TTL_SECONDS="0")
    with pytest.raises(ValidationError, match="STORAGE_SIGNED_URL_TTL_SECONDS must be between 1 and 3600"):
        Settings()


def test_storage_signed_url_ttl_valid_passes(monkeypatch):
    _set_valid_prod_env(monkeypatch, STORAGE_SIGNED_URL_TTL_SECONDS="900")
    settings = Settings()
    assert settings.storage_signed_url_ttl_seconds == 900


def test_storage_signed_url_ttl_defaults_to_one_hour(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    settings = Settings()
    assert settings.storage_signed_url_ttl_seconds == 3600


def test_storage_signed_url_ttl_non_integer_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, STORAGE_SIGNED_URL_TTL_SECONDS="abc")
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        Settings()


def test_export_ttl_days_default_is_seven(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    settings = Settings()
    assert settings.export_ttl_days == 7


def test_export_ttl_days_zero_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, EXPORT_TTL_DAYS="0")
    with pytest.raises(ValidationError, match="EXPORT_TTL_DAYS must be > 0"):
        Settings()


def test_export_ttl_days_non_integer_fails(monkeypatch):
    _set_valid_prod_env(monkeypatch, EXPORT_TTL_DAYS="abc")
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
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
