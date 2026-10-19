from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


_ALLOWED_ORIGIN = "http://localhost:8000"


async def _request(app, method: str, path: str, **kwargs):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_cors_simple_get_allows_browser_origin(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(
            app,
            "GET",
            "/api/v1/alive",
            headers={"Origin": _ALLOWED_ORIGIN},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_post_with_authorization_and_request_id_preflight_is_explicit(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(
            app,
            "OPTIONS",
            "/api/v1/auth/me",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, X-Request-ID",
            },
        )
    finally:
        get_settings.cache_clear()

    allow_methods = response.headers["access-control-allow-methods"]
    allow_headers = response.headers["access-control-allow-headers"]

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert "GET" in allow_methods
    assert "POST" in allow_methods
    assert "PATCH" in allow_methods
    assert "PUT" in allow_methods
    assert "DELETE" in allow_methods
    assert "OPTIONS" in allow_methods
    assert "*" not in allow_methods
    assert "authorization" in allow_headers.lower()
    assert "content-type" in allow_headers.lower()
    assert "x-request-id" in allow_headers.lower()
    assert "*" not in allow_headers


async def test_cors_put_preflight_remains_allowed_for_existing_browser_clients(monkeypatch):
    get_settings.cache_clear()
    app = create_app()

    try:
        response = await _request(
            app,
            "OPTIONS",
            "/api/v1/work-catalog/work-types/sample/settings",
            headers={
                "Origin": _ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _ALLOWED_ORIGIN
    assert "PUT" in response.headers["access-control-allow-methods"]
