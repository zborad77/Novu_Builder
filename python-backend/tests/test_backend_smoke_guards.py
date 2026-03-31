from unittest.mock import AsyncMock, patch

import builtins

import pytest

from app.core.config import get_settings
from app.ai.analysis_service import get_analysis_provider
from app.main import create_app


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
        "REDIS_URL": _STRONG_REDIS,
        "METRICS_AUTH_TOKEN": _STRONG_METRICS,
        "METRICS_AUTH_ENABLED": "true",
        "DATABASE_URL": _STRONG_DB,
        "APP_BASE_URL": _STRONG_BASE_URL,
        "CORS_ALLOWED_ORIGINS": _STRONG_CORS,
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": _STRONG_S3_BUCKET,
        "S3_REGION": _STRONG_S3_REGION,
    }
    env.update(overrides)
    for key, val in env.items():
        if val is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, val)
    get_settings.cache_clear()


async def test_create_app_lifespan_startup_smoke():
    app = create_app()

    async with app.router.lifespan_context(app):
        assert app.state.startup_checks == {
            "database": "ok",
            "schema": "ok",
            "storage": "ok",
        }


async def test_create_app_lifespan_fails_fast_when_storage_validation_fails_in_production():
    app = create_app()

    with (
        patch("app.main.verify_storage_health", new=AsyncMock(side_effect=RuntimeError("s3 down"))),
        patch("app.main._is_strict_startup_environment", return_value=True),
    ):
        with pytest.raises(RuntimeError, match="storage"):
            async with app.router.lifespan_context(app):
                pass


async def test_openapi_smoke_exposes_key_runtime_paths(app_client):
    response = await app_client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "/api/v1/health" in paths
    assert "get" in paths["/api/v1/health"]
    assert "/api/v1/ready" in paths
    assert "get" in paths["/api/v1/ready"]

    assert "/api/v1/cases" in paths
    assert "get" in paths["/api/v1/cases"]
    assert "post" in paths["/api/v1/cases"]

    assert "/api/v1/cases/{case_id}" in paths
    assert "get" in paths["/api/v1/cases/{case_id}"]

    assert "/api/v1/pricebooks" in paths
    assert "get" in paths["/api/v1/pricebooks"]

    assert "/api/v1/material-catalog" in paths
    assert "get" in paths["/api/v1/material-catalog"]

    assert "/api/v1/auth/me" in paths
    assert "get" in paths["/api/v1/auth/me"]


async def test_health_and_alive_smoke(app_client):
    alive = await app_client.get("/api/v1/alive")
    assert alive.status_code == 200
    assert alive.json() == {"status": "alive"}

    health = await app_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "python-backend"}

    ready = await app_client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "python-backend"}


async def test_auth_me_requires_bearer_token(app_client):
    response = await app_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_auth_me_smoke_with_valid_token(app_client, token_a):
    response = await app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["email"] == "manager_a@test.local"
    assert body["organizationId"] == "org_e2e_a"
    assert body["isSuperAdmin"] is False


async def test_cases_list_and_detail_smoke(app_client, token_a, case_a_id):
    headers = {"Authorization": f"Bearer {token_a}"}

    list_response = await app_client.get("/api/v1/cases", headers=headers)
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert isinstance(list_body["items"], list)
    assert any(item["id"] == case_a_id for item in list_body["items"])

    detail_response = await app_client.get(f"/api/v1/cases/{case_a_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == case_a_id
    assert "workflowStatus" in detail_body


def test_create_app_fails_fast_when_prometheus_client_missing_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setattr("app.main.PROMETHEUS_CLIENT_AVAILABLE", False)

    with pytest.raises(RuntimeError, match=r"^Startup validation failed \[metrics\]:"):
        create_app()

    get_settings.cache_clear()


def test_create_app_fails_fast_when_rate_limit_handler_missing_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch)
    monkeypatch.setattr("app.main._rate_limit_exceeded_handler", None)
    monkeypatch.setattr("app.main.RateLimitExceeded", None)

    with pytest.raises(RuntimeError, match=r"^Startup validation failed \[rate_limiter\]:"):
        create_app()

    get_settings.cache_clear()


def test_create_app_fails_fast_when_sentry_sdk_missing_in_production(monkeypatch):
    _set_valid_prod_env(monkeypatch, SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/1")
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            raise ModuleNotFoundError("No module named 'sentry_sdk'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match=r"^Startup validation failed \[sentry\]:"):
        create_app()

    get_settings.cache_clear()


def test_create_app_tolerates_missing_sentry_sdk_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/1")
    get_settings.cache_clear()
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            raise ModuleNotFoundError("No module named 'sentry_sdk'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    app = create_app()

    assert app is not None
    get_settings.cache_clear()


def test_runtime_provider_lookup_blocks_openai_even_if_startup_guard_is_bypassed():
    with pytest.raises(ValueError, match="blocked"):
        get_analysis_provider("openai")
