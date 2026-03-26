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
    s = Settings()
    assert s.jwt_secret == _CUSTOM_SECRET
