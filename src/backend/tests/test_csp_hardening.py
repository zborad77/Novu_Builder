from httpx import ASGITransport, AsyncClient
from fastapi.responses import HTMLResponse

from app.core.config import Settings, get_settings
from app.main import build_content_security_policy, create_app


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
        "RATE_LIMIT_MARKER_WRITE": "30/minute",
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


async def _request(app, path: str):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def test_all_success_responses_include_csp_header(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(app, "/api/v1/alive")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == build_content_security_policy()


async def test_404_response_includes_csp_header(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(app, "/api/v1/does-not-exist")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404
    assert response.headers["Content-Security-Policy"] == build_content_security_policy()


async def test_unhandled_exception_response_includes_csp_header(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    @app.get("/__csp-test-error")
    async def csp_test_error():
        raise RuntimeError("boom")

    try:
        response = await _request(app, "/__csp-test-error")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["Content-Security-Policy"] == build_content_security_policy()


async def test_inline_script_payload_is_blocked_by_csp_policy(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    @app.get("/__csp-test-inline-script")
    async def csp_test_inline_script():
        return HTMLResponse("<html><body><script>window.__xss = true</script></body></html>")

    try:
        response = await _request(app, "/__csp-test-inline-script")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert "<script>window.__xss = true</script>" in response.text
    assert response.headers["Content-Security-Policy"] == build_content_security_policy()
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]


async def test_csp_header_can_be_disabled_only_via_explicit_config(monkeypatch):
    monkeypatch.setenv("CSP_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(app, "/api/v1/alive")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers


def test_csp_enabled_defaults_true_in_production_when_flag_is_omitted(monkeypatch):
    _set_valid_prod_env(monkeypatch, CSP_ENABLED=None)

    try:
        settings = Settings()
    finally:
        get_settings.cache_clear()

    assert settings.csp_enabled is True
