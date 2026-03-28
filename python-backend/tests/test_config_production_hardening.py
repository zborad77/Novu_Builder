# =============================================================================
# Production startup hardening tests
#
# Verify that Settings raises ValidationError for missing or placeholder
# values of METRICS_AUTH_TOKEN, REDIS_URL and DATABASE_URL in production,
# and that dev / test environments remain tolerant.
# =============================================================================
import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_JWT = "a-very-strong-jwt-secret-for-testing-x99-minimum-32chars!"
_STRONG_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS = "a-strong-metrics-token-xyz-for-testing-123456789"
_STRONG_DB = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"


def _set_valid_prod_env(monkeypatch, **overrides):
    """Set the minimum set of env vars that satisfy all production validators."""
    env = {
        "APP_ENV": "production",
        "JWT_SECRET": _STRONG_JWT,
        "REDIS_URL": _STRONG_REDIS,
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "METRICS_AUTH_ENABLED": "true",
        "DATABASE_URL": _STRONG_DB,
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
