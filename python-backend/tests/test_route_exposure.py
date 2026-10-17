"""F3.1/F3.2: every route is classified, and each zone serves exactly its routes.

These tests are the CI gate for the API exposure matrix: adding a route without
classifying it in app/core/exposure.py fails here, and any route a zone does not
list answers 404 before authentication.
"""

from __future__ import annotations

import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exposure import (
    EXPOSURE,
    NOWHERE,
    PRODUCTION_ZONES,
    ZONE_ADMIN,
    ZONE_DESKTOP,
    ZONE_GATEWAY,
    ExposureGuardMiddleware,
    is_exposed,
)

# Debug-only documentation routes exist only when APP_DEBUG=true.
_DEBUG_ONLY = {
    ("GET", "/docs"),
    ("HEAD", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("HEAD", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("HEAD", "/redoc"),
}

_SYSTEM_PREFIXES = (
    "/api/v1/admin",
    "/api/v1/metrics",
    "/api/v1/health/internal",
    "/api/v1/ready",
    "/api/v1/alive",
)

# Approved size of the gateway (web) surface. Changing it is a security review:
# update API_EXPOSURE_MATRIX.md and this number together.
_APPROVED_GATEWAY_ROUTE_COUNT = 86


def _app_routes() -> set[tuple[str, str]]:
    from app.main import app

    routes = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            routes.add((method, route.path))
    return routes


def test_every_route_is_classified():
    unclassified = sorted(_app_routes() - EXPOSURE.keys())
    assert not unclassified, f"Classify in app/core/exposure.py: {unclassified}"


def test_exposure_table_has_no_stale_entries():
    stale = sorted(EXPOSURE.keys() - _app_routes() - _DEBUG_ONLY)
    assert not stale, f"Routes no longer exist: {stale}"


def test_system_and_admin_routes_are_never_reachable_from_gateway_or_desktop():
    for (method, path), zones in EXPOSURE.items():
        if path.startswith(_SYSTEM_PREFIXES) or path == "/api/v1/":
            assert ZONE_GATEWAY not in zones, (method, path)
            assert ZONE_DESKTOP not in zones, (method, path)


def test_development_routes_are_in_no_production_zone():
    for (method, path), zones in EXPOSURE.items():
        if not path.startswith("/api/v1/"):
            assert zones == NOWHERE, (method, path)


def test_gateway_surface_matches_the_approved_size():
    gateway = sorted(key for key, zones in EXPOSURE.items() if ZONE_GATEWAY in zones)
    assert len(gateway) == _APPROVED_GATEWAY_ROUTE_COUNT, gateway


def test_retired_self_service_reset_is_exposed_nowhere():
    assert EXPOSURE[("POST", "/api/v1/auth/forgot-password")] == NOWHERE
    assert EXPOSURE[("POST", "/api/v1/auth/reset-password")] == NOWHERE


@pytest.mark.parametrize("zone", sorted(PRODUCTION_ZONES))
async def test_unclassified_route_is_blocked_in_every_production_zone(zone, monkeypatch):
    from app.core.config import get_settings

    probe = FastAPI()

    @probe.get("/api/v1/not-in-the-table")
    async def unlisted() -> dict:
        return {"reachable": True}

    probe.add_middleware(ExposureGuardMiddleware)
    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://core") as client:
        response = await client.get("/api/v1/not-in-the-table")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


async def test_unclassified_route_is_reachable_only_in_dev_zone(monkeypatch):
    from app.core.config import get_settings

    probe = FastAPI()

    @probe.get("/api/v1/not-in-the-table")
    async def unlisted() -> dict:
        return {"reachable": True}

    probe.add_middleware(ExposureGuardMiddleware)
    monkeypatch.setattr(get_settings(), "nc_zone", "dev")
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://core") as client:
        assert (await client.get("/api/v1/not-in-the-table")).status_code == 200


async def test_missing_zone_outside_development_serves_nothing(monkeypatch):
    from app.core.config import get_settings

    probe = FastAPI()

    @probe.get("/api/v1/auth/me")
    async def me() -> dict:
        return {"reachable": True}

    probe.add_middleware(ExposureGuardMiddleware)
    monkeypatch.setattr(get_settings(), "nc_zone", "")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    async with AsyncClient(transport=ASGITransport(app=probe), base_url="http://core") as client:
        assert (await client.get("/api/v1/auth/me")).status_code == 404


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


_ROUTES = sorted(EXPOSURE.keys() - _DEBUG_ONLY)


@pytest.mark.parametrize("zone", sorted(PRODUCTION_ZONES))
async def test_each_zone_serves_exactly_its_routes(app_client, zone, monkeypatch):
    """Every zone x route combination, unauthenticated.

    Exposed routes reach routing/authentication (401, 422, 200, ...); everything
    else is the guard's 404, indistinguishable from an unknown URL.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    wrong = []
    for method, path in _ROUTES:
        response = await app_client.request(method, _concrete(path))
        blocked = response.status_code == 404 and response.content in (b'{"detail":"Not Found"}', b"")
        if blocked == is_exposed(zone, method, path):
            wrong.append((method, path, response.status_code))
    assert not wrong, f"zone={zone}: {wrong}"


@pytest.mark.parametrize("zone", [ZONE_GATEWAY, ZONE_DESKTOP])
async def test_cors_preflight_cannot_probe_admin_routes(app_client, zone, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nc_zone", zone)
    response = await app_client.options(
        "/api/v1/admin/users",
        headers={"Origin": "https://app.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 404


async def test_headers_cannot_select_a_zone(app_client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nc_zone", ZONE_DESKTOP)
    response = await app_client.get(
        "/api/v1/admin/users",
        headers={"X-NC-Zone": "admin", "X-Novu-Zone": "admin", "Host": "admin.internal", "X-Forwarded-For": "10.51.0.10"},
    )
    assert response.status_code == 404
    assert ZONE_ADMIN in EXPOSURE[("GET", "/api/v1/admin/users")]
