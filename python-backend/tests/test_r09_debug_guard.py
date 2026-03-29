"""R-09: APP_DEBUG default and production guard tests."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings

_STRONG_JWT = "a-strong-secret-that-is-not-the-default-value-99!"
_STRONG_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_STRONG_METRICS = "a-strong-metrics-token-xyz-for-testing-123456789"


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
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET", _STRONG_JWT)
    with pytest.raises(ValidationError, match="APP_DEBUG=True is not allowed"):
        Settings()


def test_debug_false_allowed_in_production(monkeypatch):
    """APP_DEBUG=False (default) is allowed in production."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET", _STRONG_JWT)
    monkeypatch.setenv("REDIS_URL", _STRONG_REDIS)
    monkeypatch.setenv("METRICS_AUTH_TOKEN", _STRONG_METRICS)
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "my-production-bucket")
    s = Settings()
    assert s.app_debug is False
