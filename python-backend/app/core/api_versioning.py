"""API versioning middleware for Qt desktop client compatibility.

Qt apps are compiled and installed on customer machines. They cannot be
force-updated. In practice, 2–3 versions of the Qt client will be active
simultaneously in production.

Contract (enforced from day one):
    - Never remove a response field (only add new ones)
    - Never rename a field
    - Never change field semantics
    - Only additive schema changes are permitted

This middleware:
    1. Reads X-Client-Version header from incoming requests
    2. Injects X-Api-Version into every response
    3. Logs version mismatches for compatibility monitoring
    4. Returns X-Api-Deprecated-Warning when client is behind

Enforcement: this is observability + logging only — no hard rejection.
Hard rejection comes only when a client version is explicitly sunset
(added to SUNSET_CLIENT_VERSIONS set).
"""
from __future__ import annotations

from packaging.version import Version, InvalidVersion
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Current API version — increment when a new mandatory feature is added
CURRENT_API_VERSION = "1"

# Minimum supported Qt client version — clients below this get a warning header
MIN_SUPPORTED_CLIENT_VERSION = "1.0.0"

# Explicitly sunset client versions — these receive 410 Gone
# Format: "major.minor.patch"
SUNSET_CLIENT_VERSIONS: frozenset[str] = frozenset()


class ApiVersioningMiddleware(BaseHTTPMiddleware):
    """Injects API version headers and logs client version drift."""

    async def dispatch(self, request: Request, call_next) -> Response:
        client_version_raw = request.headers.get("X-Client-Version")

        # Pass through, then decorate response
        response: Response = await call_next(request)

        response.headers["X-Api-Version"] = CURRENT_API_VERSION

        if client_version_raw:
            _annotate_for_client_version(response, client_version_raw, request)

        return response


def _annotate_for_client_version(
    response: Response, client_version_raw: str, request: Request
) -> None:
    client_version_raw = client_version_raw.strip()

    if client_version_raw in SUNSET_CLIENT_VERSIONS:
        # Caller must check for 410 — this client is no longer supported
        response.headers["X-Api-Deprecated-Warning"] = (
            f"Client version {client_version_raw} is sunset. Please upgrade."
        )
        logger.warning(
            "api_versioning.sunset_client",
            client_version=client_version_raw,
            path=request.url.path,
        )
        return

    try:
        client_v = Version(client_version_raw)
        min_v = Version(MIN_SUPPORTED_CLIENT_VERSION)
    except InvalidVersion:
        logger.debug(
            "api_versioning.unparseable_client_version",
            client_version=client_version_raw,
        )
        return

    if client_v < min_v:
        response.headers["X-Api-Deprecated-Warning"] = (
            f"Client version {client_version_raw} is below minimum supported "
            f"version {MIN_SUPPORTED_CLIENT_VERSION}. Please upgrade."
        )
        logger.info(
            "api_versioning.outdated_client",
            client_version=str(client_v),
            min_version=MIN_SUPPORTED_CLIENT_VERSION,
            path=request.url.path,
        )
