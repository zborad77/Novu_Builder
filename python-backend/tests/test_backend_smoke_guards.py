from unittest.mock import AsyncMock, MagicMock, patch

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
_STRONG_SENTRY_DSN = "https://7f9c0d3a2b1e4f56a789bc123def4567@o123456.ingest.sentry.io/987654"


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
        "BACKPRESSURE_MAX_CONCURRENT_JOBS": "0",
        "BACKPRESSURE_MAX_QUEUED_JOBS": "0",
        "BACKPRESSURE_MAX_RETRY_INFLIGHT": "0",
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
        "RATE_LIMIT_READ_LIST": "120/minute",
        "RATE_LIMIT_READ_DETAIL": "60/minute",
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
    health_data = health.json()
    assert health_data["service"] == "python-backend"
    assert health_data["status"] in {"ok", "degraded"}
    assert "security" in health_data
    assert "authProtection" in health_data["security"]

    ready = await app_client.get("/api/v1/ready")
    assert ready.status_code == 200
    ready_data = ready.json()
    assert ready_data["service"] == "python-backend"
    assert ready_data["status"] in {"ready", "degraded"}


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
    _set_valid_prod_env(monkeypatch, SENTRY_DSN=_STRONG_SENTRY_DSN)
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
    monkeypatch.setenv("SENTRY_DSN", _STRONG_SENTRY_DSN)
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


def test_create_app_initializes_sentry_with_configured_sampling(monkeypatch):
    _set_valid_prod_env(
        monkeypatch,
        SENTRY_DSN=_STRONG_SENTRY_DSN,
        SENTRY_TRACES_SAMPLE_RATE="0.2",
        SENTRY_PROFILES_SAMPLE_RATE="0.1",
    )
    sentry_sdk = MagicMock()

    app = None
    try:
        with patch("app.main.verify_runtime_dependency_guards", return_value=sentry_sdk):
            app = create_app()
    finally:
        get_settings.cache_clear()

    assert app is not None
    sentry_sdk.init.assert_called_once()
    assert sentry_sdk.init.call_args.kwargs["traces_sample_rate"] == 0.2
    assert sentry_sdk.init.call_args.kwargs["profiles_sample_rate"] == 0.1


def test_create_app_uses_configured_app_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9-test")
    get_settings.cache_clear()

    try:
        app = create_app()
    finally:
        get_settings.cache_clear()

    assert app.version == "9.9.9-test"


def test_runtime_provider_lookup_blocks_openai_even_if_startup_guard_is_bypassed():
    with pytest.raises(ValueError, match="blocked"):
        get_analysis_provider("openai")
