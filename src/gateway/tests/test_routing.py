"""Povrch gateway: /bff/health, 404 pro vše ostatní, allowlist a traversal (bez Redisu)."""

from __future__ import annotations

import pytest

from tests.conftest import Harness, asgi_request


async def test_health_returns_only_status(offline_harness: Harness) -> None:
    async with offline_harness.client() as client:
        response = await client.get("/bff/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert offline_harness.core.requests == []


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/api/v1/cases",
        "/api/v1/auth/login",
        "/docs",
        "/openapi.json",
        "/metrics",
        "/admin",
        "/admin/users",
        "/redoc",
        "/bff",
        "/bff/",
        "/bff/unknown",
        "/bff/api",
        "/bff/healthz",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_everything_else_is_404(offline_harness: Harness, path: str, method: str) -> None:
    async with offline_harness.client() as client:
        response = await client.request(method, path)
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found."
    assert "requestId" in response.json()
    assert offline_harness.core.requests == []


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/bff/auth/login"),
        ("PUT", "/bff/auth/login"),
        ("GET", "/bff/auth/logout"),
        ("POST", "/bff/session"),
        ("HEAD", "/bff/health"),
        ("OPTIONS", "/bff/health"),
        ("OPTIONS", "/bff/auth/login"),
    ],
)
async def test_wrong_method_on_bff_endpoint_is_404(offline_harness: Harness, method: str, path: str) -> None:
    response = await asgi_request(offline_harness.app, method, path.encode())
    assert response.status == 404


@pytest.mark.parametrize(
    "path",
    [
        "/bff/api/unknown",
        "/bff/api/admin/users",
        "/bff/api/admin/companies",
        "/bff/api/auth/login",
        "/bff/api/auth/me",
        "/bff/api/auth/refresh",
        "/bff/api/auth/sessions",
        "/bff/api/internal/security-events",
    ],
)
async def test_not_passthrough_routes_are_404(offline_harness: Harness, path: str) -> None:
    for method in ("GET", "POST"):
        response = await asgi_request(offline_harness.app, method, path.encode())
        assert response.status == 404, (method, path)
    assert offline_harness.core.requests == []
    events = [e for e in offline_harness.app.events.pending if e["type"] == "allowlist_miss"]
    assert len(events) == 2
    assert events[0]["detail"]["path"] == path


@pytest.mark.parametrize(
    "raw_path",
    [
        b"/bff/api/cases/..",
        b"/bff/api/cases/../admin/users",
        b"/bff/api/cases/./x",
        b"/bff/api/cases/%2e%2e",
        b"/bff/api/cases/%2E%2E/admin",
        b"/bff/api/cases/a%2Fb",
        b"/bff/api/cases/a%2fb",
        b"/bff/api/cases/..%2Fadmin",
        b"/bff/api/cases/a%5Cb",
        b"/bff/api/cases/a%5cb",
        b"/bff/api/cases/a%00",
        b"/bff/api/cases/a\\b",
        b"/bff/api/cases//",
        b"/bff/api//cases",
        b"/bff/api/cases/",
        b"/bff/api/cases/%41",
        b"/bff/api/../api/v1/cases",
    ],
)
async def test_traversal_variants_are_404(offline_harness: Harness, raw_path: bytes) -> None:
    response = await asgi_request(offline_harness.app, "GET", raw_path)
    assert response.status == 404
    assert offline_harness.core.requests == []


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "TRACE", "CONNECT"])
async def test_forbidden_methods_on_api_are_404(offline_harness: Harness, method: str) -> None:
    response = await asgi_request(
        offline_harness.app,
        method,
        b"/bff/api/cases",
        headers=[("Origin", "https://evil.example"), ("Access-Control-Request-Method", "POST")],
    )
    assert response.status == 404
    assert response.header("access-control-allow-origin") is None


async def test_redis_unavailable_returns_503(offline_harness: Harness) -> None:
    cookie = {"Cookie": "__Host-nc_sid=" + "a" * 43}
    async with offline_harness.client() as client:
        api = await client.get("/bff/api/cases", headers=cookie)
        session = await client.get("/bff/session", headers=cookie)
        login = await client.post(
            "/bff/auth/login",
            json={"email": "a@b.cz", "password": "x"},
            headers={"Origin": "https://nc.example.test"},
        )
        health = await client.get("/bff/health")
    assert api.status_code == 503
    assert session.status_code == 503
    assert login.status_code == 503
    assert api.json()["detail"] == "Service temporarily unavailable."
    assert health.status_code == 200
    # fail closed: core se bez session store vůbec nevolá
    assert offline_harness.core.requests == []


async def test_websocket_is_refused(offline_harness: Harness) -> None:
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await offline_harness.app({"type": "websocket", "path": "/bff/api/cases", "headers": []}, receive, send)
    assert sent == [{"type": "websocket.close", "code": 1008}]
