"""Network zones and the API exposure table (F3.1/F3.2, docs/security/API_EXPOSURE_MATRIX.md).

Each production API process serves exactly one zone, fixed by its configuration
(``NC_ZONE``) — never by anything in the request. ``exposure_guard`` answers 404
for every route the zone does not list, before authentication or any handler
runs. Routes missing from ``EXPOSURE`` are blocked in every production zone,
admin included; CI (tests/test_route_exposure.py) fails on any unclassified route.

Zones:
  gateway  – reached only by the Public Edge gateway (F4); web users
  desktop  – reached by enrolled desktop WireGuard peers
  admin    – reached by NovuAdmin / monitoring WireGuard peers
  dev      – local development and tests only: every route, refused in production
"""

from __future__ import annotations

from typing import Final

from starlette.responses import JSONResponse
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

ZONE_GATEWAY: Final = "gateway"
ZONE_DESKTOP: Final = "desktop"
ZONE_ADMIN: Final = "admin"
ZONE_DEV: Final = "dev"

PRODUCTION_ZONES: Final = frozenset({ZONE_GATEWAY, ZONE_DESKTOP, ZONE_ADMIN})
ALL_ZONES: Final = PRODUCTION_ZONES | {ZONE_DEV}

# JWT audience issued and accepted by each zone (F3.3). A token never crosses zones.
AUDIENCE_BY_ZONE: Final = {
    ZONE_GATEWAY: "nc-web",
    ZONE_DESKTOP: "nc-desktop",
    ZONE_ADMIN: "nc-admin",
    ZONE_DEV: "nc-dev",
}

# Zones where a superadmin may authenticate.
SUPERADMIN_ZONES: Final = frozenset({ZONE_ADMIN, ZONE_DEV})

_G, _D, _A = ZONE_GATEWAY, ZONE_DESKTOP, ZONE_ADMIN
TENANT: Final = frozenset({_G, _D})
AUTH: Final = frozenset({_G, _D, _A})
SYSTEM: Final = frozenset({_A})
NOWHERE: Final = frozenset[str]()

_P = "/api/v1"

# (method, route template) -> zones. Keep in sync with API_EXPOSURE_MATRIX.md.
EXPOSURE: Final[dict[tuple[str, str], frozenset[str]]] = {
    # ── System / operations ───────────────────────────────────────────────
    ("GET", f"{_P}/"): SYSTEM,
    ("GET", f"{_P}/alive"): SYSTEM,
    # Desktop's server-setup dialog probes /health (desktop-qt serversetupdialog.cpp).
    ("GET", f"{_P}/health"): frozenset({_D, _A}),
    ("GET", f"{_P}/health/internal"): SYSTEM,
    ("GET", f"{_P}/ready"): SYSTEM,
    ("GET", f"{_P}/ready/processing"): SYSTEM,
    ("GET", f"{_P}/metrics"): SYSTEM,
    # ── Authentication ───────────────────────────────────────────────────
    ("POST", f"{_P}/auth/login"): AUTH,
    ("POST", f"{_P}/auth/refresh"): AUTH,
    ("POST", f"{_P}/auth/logout"): AUTH,
    ("GET", f"{_P}/auth/me"): AUTH,
    ("POST", f"{_P}/auth/change-password"): AUTH,
    ("GET", f"{_P}/auth/sessions"): AUTH,
    ("DELETE", f"{_P}/auth/sessions/{{session_id}}"): AUTH,
    # Retired (410); public self-service reset arrives with the gateway in F4 (D-05).
    ("POST", f"{_P}/auth/forgot-password"): NOWHERE,
    ("POST", f"{_P}/auth/reset-password"): NOWHERE,
    # ── Administration (superadmin; company admins per RBAC) — D-10 open ──
    ("GET", f"{_P}/admin/audit"): SYSTEM,
    ("GET", f"{_P}/admin/companies"): SYSTEM,
    ("POST", f"{_P}/admin/companies"): SYSTEM,
    ("GET", f"{_P}/admin/companies/{{company_id}}"): SYSTEM,
    ("PATCH", f"{_P}/admin/companies/{{company_id}}"): SYSTEM,
    ("POST", f"{_P}/admin/impersonate/{{user_id}}"): SYSTEM,
    ("GET", f"{_P}/admin/jobs"): SYSTEM,
    ("GET", f"{_P}/admin/jobs/{{job_id}}"): SYSTEM,
    ("POST", f"{_P}/admin/jobs/{{job_id}}/reprocess"): SYSTEM,
    ("POST", f"{_P}/admin/jobs/{{job_id}}/retry"): SYSTEM,
    ("GET", f"{_P}/admin/logs"): SYSTEM,
    ("POST", f"{_P}/admin/photos/{{photo_id}}/purge"): SYSTEM,
    ("GET", f"{_P}/admin/users"): SYSTEM,
    ("POST", f"{_P}/admin/users"): SYSTEM,
    ("GET", f"{_P}/admin/users/{{user_id}}"): SYSTEM,
    ("PATCH", f"{_P}/admin/users/{{user_id}}"): SYSTEM,
    ("POST", f"{_P}/admin/users/{{user_id}}/reset-password"): SYSTEM,
    # ── Cases and workflow ───────────────────────────────────────────────
    ("GET", f"{_P}/cases"): TENANT,
    ("POST", f"{_P}/cases"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}/activity/stream"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/approve-proposal"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/archive"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/cancel"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/duplicate"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/final-proposal"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/proposal-draft"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/return-to-draft"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/send"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/start-analysis"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/submit"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}/timeline"): TENANT,
    # ── Analysis ─────────────────────────────────────────────────────────
    ("GET", f"{_P}/cases/{{case_id}}/analysis-jobs"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/analysis-jobs"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/analysis-results/{{result_id}}/selection"): TENANT,
    ("GET", f"{_P}/analysis-jobs/{{job_id}}"): TENANT,
    ("POST", f"{_P}/analysis-jobs/{{job_id}}/cancel"): TENANT,
    ("POST", f"{_P}/analysis-jobs/{{job_id}}/retry"): TENANT,
    # ── Estimates, exports ───────────────────────────────────────────────
    ("GET", f"{_P}/cases/{{case_id}}/estimates"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/estimates/recalculate"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/exports/case-zip"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/exports/proposal-docx"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/exports/quote-docx"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/exports/quote-pdf"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/exports/report-pdf"): TENANT,
    ("GET", f"{_P}/exports/{{export_id}}"): TENANT,
    # ── Photos, measurements, markers ────────────────────────────────────
    ("GET", f"{_P}/cases/{{case_id}}/images"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/images"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}/images/deleted"): TENANT,
    ("DELETE", f"{_P}/cases/{{case_id}}/images/{{image_id}}"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/images/{{image_id}}/analysis-reference"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/images/{{image_id}}/move"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/images/{{image_id}}/primary"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/images/{{image_id}}/purge"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/images/{{image_id}}/restore"): TENANT,
    ("GET", f"{_P}/images/{{image_id}}/preview"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/measurements"): TENANT,
    ("PATCH", f"{_P}/measurements/{{measurement_id}}"): TENANT,
    ("POST", f"{_P}/measurements/{{measurement_id}}/confirm"): TENANT,
    ("GET", f"{_P}/markers"): TENANT,
    ("POST", f"{_P}/markers"): TENANT,
    ("DELETE", f"{_P}/markers/{{marker_id}}"): TENANT,
    # ── Work items and catalogs ──────────────────────────────────────────
    ("GET", f"{_P}/cases/{{case_id}}/work-items"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/work-items"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}/detections"): TENANT,
    ("PATCH", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}/values"): TENANT,
    ("PUT", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}/values"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}/values/confirm"): TENANT,
    ("POST", f"{_P}/cases/{{case_id}}/work-items/{{project_work_item_id}}/values/merge"): TENANT,
    ("GET", f"{_P}/cases/{{case_id}}/work-types/{{work_type_code}}/effective-configuration"): TENANT,
    ("GET", f"{_P}/work-catalog/catalog/categories"): TENANT,
    ("GET", f"{_P}/work-catalog/catalog/grouped"): TENANT,
    ("GET", f"{_P}/work-catalog/catalog/work-types"): TENANT,
    ("GET", f"{_P}/work-catalog/catalog/work-types/{{work_type_code}}"): TENANT,
    ("GET", f"{_P}/work-catalog/catalog/work-types/{{work_type_code}}/parameters/{{parameter_code}}"): TENANT,
    ("GET", f"{_P}/work-catalog/work-types"): TENANT,
    ("GET", f"{_P}/work-catalog/work-types/{{work_type_code}}/effective"): TENANT,
    ("PUT", f"{_P}/work-catalog/work-types/{{work_type_code}}/settings"): TENANT,
    ("GET", f"{_P}/material-catalog"): TENANT,
    ("PATCH", f"{_P}/material-catalog/{{material_id}}"): TENANT,
    ("GET", f"{_P}/material-catalog/{{material_id}}/supplier-prices"): TENANT,
    ("GET", f"{_P}/pricebooks"): TENANT,
    ("POST", f"{_P}/pricebooks"): TENANT,
    ("GET", f"{_P}/pricebooks/{{pricebook_id}}/items"): TENANT,
    ("GET", f"{_P}/suppliers"): TENANT,
    ("PATCH", f"{_P}/suppliers/{{supplier_id}}"): TENANT,
    # ── Offer pipeline ───────────────────────────────────────────────────
    ("POST", f"{_P}/offer-requests"): TENANT,
    ("GET", f"{_P}/offer-requests/{{offer_id}}"): TENANT,
    ("PATCH", f"{_P}/offer-requests/{{offer_id}}"): TENANT,
    ("POST", f"{_P}/offer-requests/{{offer_id}}/cancel"): TENANT,
    ("POST", f"{_P}/offer-requests/{{offer_id}}/more-info"): TENANT,
    ("GET", f"{_P}/offer-requests/{{offer_id}}/events"): TENANT,
    ("GET", f"{_P}/offer-requests/{{offer_id}}/result"): TENANT,
    ("GET", f"{_P}/offer-requests/{{offer_id}}/status"): TENANT,
    # ── Development only (never in a production zone) ────────────────────
    ("GET", "/mock-storage/{file_path:path}"): NOWHERE,
    ("GET", "/openapi.json"): NOWHERE,
    ("HEAD", "/openapi.json"): NOWHERE,
    ("GET", "/docs"): NOWHERE,
    ("HEAD", "/docs"): NOWHERE,
    ("GET", "/docs/oauth2-redirect"): NOWHERE,
    ("HEAD", "/docs/oauth2-redirect"): NOWHERE,
    ("GET", "/redoc"): NOWHERE,
    ("HEAD", "/redoc"): NOWHERE,
}


def zones_for(method: str, template: str) -> frozenset[str]:
    """Zones allowed to serve a route. Unclassified routes: none (deny by default)."""
    return EXPOSURE.get((method.upper(), template), NOWHERE)


def is_exposed(zone: str, method: str, template: str) -> bool:
    if zone == ZONE_DEV:
        return True
    return zone in zones_for(method, template)


def current_zone() -> str:
    from app.core.config import get_settings

    return get_settings().effective_nc_zone


def current_audience() -> str:
    return AUDIENCE_BY_ZONE[current_zone()]


_NOT_FOUND = JSONResponse({"detail": "Not Found"}, status_code=404)


class ExposureGuardMiddleware:
    """Answer 404 for any route this process's zone does not expose.

    The zone comes from process configuration only. Headers, client address and
    the URL host never influence it. Runs before authentication, dependencies,
    rate limiting and handlers, and looks exactly like an unknown URL.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        zone = current_zone()
        if zone not in ALL_ZONES:
            # No zone configured outside development: serve nothing (fail closed).
            await _NOT_FOUND(scope, receive, send)
            return
        if zone == ZONE_DEV:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method == "OPTIONS":
            # CORS preflight is judged by the method it asks about.
            for name, value in scope.get("headers", []):
                if name == b"access-control-request-method":
                    method = value.decode("latin-1").strip().upper() or method
                    break

        template = _match_template(scope, method)
        if template is None or not is_exposed(zone, method, template):
            await _NOT_FOUND(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _match_template(scope: Scope, method: str) -> str | None:
    app = scope.get("app")
    router = getattr(app, "router", None)
    if router is None:
        return None
    probe = dict(scope)
    probe["method"] = method
    for route in router.routes:
        match, _ = route.matches(probe)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None
