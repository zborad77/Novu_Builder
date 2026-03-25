"""
Audit trail middleware.

Logs every mutating HTTP request (POST / PATCH / PUT / DELETE) that returns
2xx as an AuditLog row.  Read-only GET calls are not logged here — they add
noise without diagnostic value.

The middleware reads the Authorization header to identify the actor.  It does
NOT call the DB auth service (that would double every DB round-trip); instead
it decodes the JWT without verification overhead — the token was already
fully verified by the route dependency.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import jwt
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory
from app.models.domain import AuditLog

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Actions we want to name explicitly instead of showing raw paths
_PATH_ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/auth/login"): "auth.login",
    ("POST", "/auth/logout"): "auth.logout",
    ("POST", "/cases"): "case.create",
    ("POST", "/cases/{id}/archive"): "case.archive",
    ("POST", "/cases/{id}/send"): "case.send",
    ("POST", "/cases/{id}/final-proposal"): "case.final_proposal",
    ("POST", "/cases/{id}/duplicate"): "case.duplicate",
    ("PATCH", "/cases/{id}"): "case.update",
    ("PATCH", "/cases/{id}/proposal-draft"): "case.proposal_draft.update",
    ("POST", "/cases/{id}/analysis-jobs"): "analysis.trigger",
    ("POST", "/analysis-jobs/{id}/cancel"): "analysis.cancel",
    ("POST", "/analysis-jobs/{id}/retry"): "analysis.retry",
    ("POST", "/cases/{id}/exports/report-pdf"): "export.report_pdf",
    ("POST", "/cases/{id}/exports/proposal-docx"): "export.proposal_docx",
    ("POST", "/cases/{id}/exports/quote-pdf"): "export.quote_pdf",
    ("POST", "/cases/{id}/exports/quote-docx"): "export.quote_docx",
    ("POST", "/cases/{id}/exports/case-zip"): "export.case_zip",
    ("DELETE", "/cases/{id}/images/{id}"): "image.delete",
    ("PATCH", "/cases/{id}/images/{id}/primary"): "image.set_primary",
    ("PATCH", "/cases/{id}/images/{id}/analysis-reference"): "image.set_analysis_reference",
    ("POST", "/admin/users"): "admin.user.create",
    ("PATCH", "/admin/users/{id}"): "admin.user.update",
    ("POST", "/admin/users/{id}/reset-password"): "admin.user.reset_password",
    ("POST", "/admin/companies"): "admin.company.create",
    ("PATCH", "/admin/companies/{id}"): "admin.company.update",
    ("POST", "/admin/impersonate/{id}"): "admin.impersonate",
    ("POST", "/admin/jobs/{id}/retry"): "admin.job.retry",
    ("PATCH", "/suppliers/{id}"): "supplier.update",
    ("POST", "/pricebooks"): "pricebook.create",
}

_SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc"}
_SKIP_PREFIXES = ("/mock-storage",)

# ── Cross-tenant denial rate limiter ────────────────────────────────────────
# Prevents log flooding when a single user probes resources in a tight loop.
# State: user_id → (window_start_monotonic, event_count_in_window)
_DENY_WINDOW_SEC: int = 60
_DENY_MAX_PER_WINDOW: int = 5
_deny_counts: dict[str, tuple[float, int]] = {}


def log_cross_tenant_denied(
    log,
    *,
    resource: str,
    resource_id: str,
    user_id: str,
    org_id: str | None,
) -> None:
    """Emit SECURITY_EVENT: cross_tenant_access_denied with per-user rate limiting.

    The first _DENY_MAX_PER_WINDOW events per user per _DENY_WINDOW_SEC are logged
    normally.  On the (max+1)-th event a single throttle notice is emitted.
    All subsequent events in the same window are silently suppressed to prevent
    log flooding during brute-force probing.
    """
    now = time.monotonic()
    window_start, count = _deny_counts.get(user_id, (now, 0))

    if now - window_start > _DENY_WINDOW_SEC:
        window_start, count = now, 0

    count += 1
    _deny_counts[user_id] = (window_start, count)

    if count <= _DENY_MAX_PER_WINDOW:
        log.warning(
            "SECURITY_EVENT: cross_tenant_access_denied",
            resource=resource,
            resource_id=resource_id,
            user_id=user_id,
            org_id=org_id,
        )
    elif count == _DENY_MAX_PER_WINDOW + 1:
        log.warning(
            "SECURITY_EVENT: cross_tenant_access_denied_throttled",
            user_id=user_id,
            org_id=org_id,
            suppressed_from_count=count,
            window_sec=_DENY_WINDOW_SEC,
        )


def _classify(method: str, path: str) -> tuple[str, str | None, str | None]:
    """Return (action, resource_type, resource_id) from method + path."""
    # Strip API prefix
    stripped = path
    for prefix in ("/api/v1",):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]

    parts = [p for p in stripped.split("/") if p]

    # Try exact match first
    for (m, pattern), action in _PATH_ACTIONS.items():
        if m != method:
            continue
        pat_parts = [p for p in pattern.split("/") if p]
        if len(pat_parts) != len(parts):
            continue
        if all(pp == p or pp.startswith("{") for pp, p in zip(pat_parts, parts)):
            # Extract resource id (second segment if it looks like an id)
            resource_type = pat_parts[0] if pat_parts else None
            resource_id = parts[1] if len(parts) > 1 and not pat_parts[1].endswith("}") is False else None
            # Simpler: just grab second part if it's not a keyword
            rid = None
            for i, (pp, p) in enumerate(zip(pat_parts, parts)):
                if pp.startswith("{") and i == 1:
                    rid = p
            return action, resource_type, rid

    # Fallback: build action from method + path
    action = f"{method.lower()}.{'.'.join(parts)}" if parts else method.lower()
    resource_type = parts[0] if parts else None
    resource_id = parts[1] if len(parts) > 1 else None
    return action, resource_type, resource_id


def _decode_user(authorization: str | None) -> tuple[str | None, str | None]:
    """Fast JWT decode (no signature verify — already done by route dep)."""
    if not authorization or not authorization.startswith("Bearer "):
        return None, None
    token = authorization[7:]
    try:
        settings = get_settings()
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub"), payload.get("impersonated_by")
    except Exception:
        return None, None


async def write_audit_log(
    session,
    *,
    current_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict,
) -> None:
    """Write a rich AuditLog entry reusing an existing DB session.

    Looks up the actor's email and org_id from the DB for full traceability.
    Failures are logged as SECURITY_EVENT warnings and do not propagate — audit
    logging must never break the main request path (fail-open). For fail-closed
    enforcement, use transactional audit writes at the repository layer.
    """
    try:
        from app.models.domain import AuditLog as _AuditLog
        from app.models.domain import User as _User

        actor = await session.get(_User, current_user_id)
        session.add(_AuditLog(
            id=uuid4().hex,
            user_id=current_user_id,
            user_email=actor.email if actor else None,
            org_id=actor.organization_id if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=json.dumps(detail, ensure_ascii=False),
            created_at=datetime.now(UTC),
        ))
        await session.commit()
    except Exception as exc:
        logger.warning(
            "SECURITY_EVENT: audit_write_failed",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            error=str(exc),
        )


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Skip non-mutating and noisy paths
        if method == "GET" or path in _SKIP_PATHS:
            return await call_next(request)
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        # Only log successful mutations
        if response.status_code < 200 or response.status_code >= 300:
            return response

        try:
            auth_header = request.headers.get("Authorization")
            user_id, impersonated_by = _decode_user(auth_header)
            action, resource_type, resource_id = _classify(method, path)
            ip = request.client.host if request.client else None

            async with AsyncSessionFactory() as session:
                async with session.begin():
                    # Enrich with email + org_id from DB (one extra SELECT, worth it)
                    user_email: str | None = None
                    org_id: str | None = None
                    if user_id:
                        from app.models.domain import User as UserModel
                        user_obj = await session.get(UserModel, user_id)
                        if user_obj:
                            user_email = user_obj.email
                            org_id = user_obj.organization_id

                    log = AuditLog(
                        id=uuid4().hex,
                        user_id=user_id,
                        user_email=user_email,
                        org_id=org_id,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        impersonated_by=impersonated_by,
                        ip=ip,
                        created_at=datetime.now(UTC),
                    )
                    session.add(log)
        except Exception as exc:
            logger.warning("audit.write_failed", error=str(exc))

        return response
