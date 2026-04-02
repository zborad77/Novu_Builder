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

from contextvars import ContextVar
from dataclasses import dataclass
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import jwt
import structlog
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.metrics import AUDIT_WRITE_FAILED_TOTAL
from app.db.session import AsyncSessionFactory
from app.models.domain import AuditLog

if TYPE_CHECKING:
    from app.schemas.auth import AuthUserRead

logger = structlog.get_logger(__name__)

AUDIT_POLICY_OPERATIONAL = "operational"
AUDIT_POLICY_SECURITY_CRITICAL = "security_critical"

# Security-critical actions either mint cross-user access or rotate credentials.
# These must fail closed if their audit trail cannot be persisted.
SECURITY_CRITICAL_AUDIT_ACTIONS: frozenset[str] = frozenset({
    "admin.impersonate",
    "admin.user.reset_password",
    "auth.change_password",
})

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

_SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc",
               # These auth endpoints identify the user from a reset token, not from a JWT.
               # Middleware would log user_id=None with a generic fallback action — useless.
               # Explicit write_audit_log() calls inside the routes carry the real user_id
               # and semantic action names (password_reset_requested / password_reset).
               "/api/v1/auth/forgot-password", "/api/v1/auth/reset-password",
               "/api/v1/auth/change-password"}
# Admin routes have explicit write_audit_log() calls with richer detail (target_email,
# target_org, etc.) — middleware logging would create duplicates with less context.
_SKIP_PREFIXES = ("/mock-storage", "/api/v1/admin")

# ── Cross-tenant denial rate limiter ────────────────────────────────────────
# Prevents log flooding when a single user probes resources in a tight loop.
# State: user_id → (window_start_monotonic, event_count_in_window)
_DENY_WINDOW_SEC: int = 60
_DENY_MAX_PER_WINDOW: int = 5
_deny_counts: dict[str, tuple[float, int]] = {}


@dataclass(frozen=True)
class _AuditActor:
    user_id: str | None
    user_email: str | None
    org_id: str | None
    impersonated_by: str | None


class SecurityAuditWriteError(RuntimeError):
    """Raised when a security-critical audit record cannot be persisted."""


_request_audit_actor: ContextVar[_AuditActor | None] = ContextVar(
    "request_audit_actor",
    default=None,
)


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
            resource_id = parts[1] if len(parts) > 1 and pat_parts[1].endswith("}") is not False else None
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


def bind_request_audit_actor(request: Request, current_user: "AuthUserRead") -> None:
    actor = _AuditActor(
        user_id=current_user.id,
        user_email=current_user.email,
        org_id=current_user.organizationId,
        impersonated_by=current_user.impersonatedBy,
    )
    request.state.audit_actor = actor
    _request_audit_actor.set(actor)


def _audit_actor_from_request(request: Request) -> _AuditActor | None:
    actor = getattr(request.state, "audit_actor", None)
    if isinstance(actor, _AuditActor):
        return actor
    return None


def _audit_actor_from_context(user_id: str | None = None) -> _AuditActor | None:
    actor = _request_audit_actor.get()
    if not isinstance(actor, _AuditActor):
        return None
    if user_id is not None and actor.user_id != user_id:
        return None
    return actor


def _audit_actor_from_scope(scope: Scope) -> _AuditActor | None:
    state = scope.get("state")
    actor = state.get("audit_actor") if isinstance(state, dict) else getattr(state, "audit_actor", None)
    if isinstance(actor, _AuditActor):
        return actor
    return _audit_actor_from_context()


async def _enrich_audit_actor(session, actor: _AuditActor | None) -> _AuditActor:
    if actor is None:
        context_actor = _audit_actor_from_context()
        if context_actor is not None:
            return context_actor
        return _AuditActor(None, None, None, None)

    context_actor = _audit_actor_from_context(actor.user_id)
    if (
        context_actor is not None
        and context_actor.user_email is not None
        and context_actor.org_id is not None
    ):
        return _AuditActor(
            user_id=actor.user_id,
            user_email=context_actor.user_email,
            org_id=context_actor.org_id,
            impersonated_by=actor.impersonated_by or context_actor.impersonated_by,
        )

    if not actor.user_id:
        return actor

    if actor.user_email is not None and actor.org_id is not None:
        return actor

    from app.models.domain import User as _User

    user_obj = await session.get(_User, actor.user_id)
    if user_obj is None:
        return actor

    enriched_actor = _AuditActor(
        user_id=actor.user_id,
        user_email=user_obj.email,
        org_id=user_obj.organization_id,
        impersonated_by=actor.impersonated_by,
    )
    _request_audit_actor.set(enriched_actor)
    return enriched_actor


async def _safe_rollback(session) -> None:
    try:
        await session.rollback()
    except Exception:
        pass


def _log_audit_write_failure(
    *,
    error: Exception,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    user_id: str | None = None,
    policy: str = AUDIT_POLICY_OPERATIONAL,
) -> None:
    AUDIT_WRITE_FAILED_TOTAL.inc()
    logger.warning(
        "SECURITY_EVENT: audit_write_failed",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        policy=policy,
        error_type=type(error).__name__,
        error=str(error),
    )


def _build_audit_log(
    *,
    actor: _AuditActor,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    detail: dict | None = None,
    ip: str | None = None,
    user_id: str | None = None,
) -> AuditLog:
    return AuditLog(
        id=uuid4().hex,
        user_id=user_id if user_id is not None else actor.user_id,
        user_email=actor.user_email,
        org_id=actor.org_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        impersonated_by=actor.impersonated_by,
        ip=ip,
        created_at=datetime.now(UTC),
    )


async def _stage_audit_log(
    session,
    *,
    actor: _AuditActor | None,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    detail: dict | None = None,
    ip: str | None = None,
    user_id: str | None = None,
) -> _AuditActor:
    enriched_actor = await _enrich_audit_actor(session, actor)
    session.add(_build_audit_log(
        actor=enriched_actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip=ip,
        user_id=user_id,
    ))
    return enriched_actor


async def write_audit_log(
    session,
    *,
    current_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict,
    policy: str = AUDIT_POLICY_OPERATIONAL,
    commit: bool = True,
) -> None:
    """Write a rich AuditLog entry reusing an existing DB session.

    Reuses request/auth actor data first; falls back to DB only when needed.
    Failures are logged as SECURITY_EVENT warnings and do not propagate — audit
    logging must never break the main request path (fail-open). For fail-closed
    enforcement, use transactional audit writes at the repository layer.
    """
    actor = _audit_actor_from_context(current_user_id)
    if actor is None:
        actor = _AuditActor(
            user_id=current_user_id,
            user_email=None,
            org_id=None,
            impersonated_by=None,
        )
    try:
        actor = await _stage_audit_log(
            session,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            user_id=current_user_id,
        )
        if commit:
            await session.commit()
    except Exception as exc:
        await _safe_rollback(session)
        _log_audit_write_failure(
            error=exc,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=current_user_id,
            policy=policy,
        )
        if policy == AUDIT_POLICY_SECURITY_CRITICAL:
            raise SecurityAuditWriteError(
                f"Security-critical audit write failed for action={action!r}."
            ) from exc


async def commit_security_critical_audit(
    session,
    *,
    current_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: dict,
) -> None:
    if action not in SECURITY_CRITICAL_AUDIT_ACTIONS:
        raise ValueError(f"Action {action!r} is not registered as security-critical.")

    try:
        await write_audit_log(
            session,
            current_user_id=current_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            policy=AUDIT_POLICY_SECURITY_CRITICAL,
            commit=False,
        )
        await session.commit()
    except SecurityAuditWriteError:
        raise
    except Exception as exc:
        await _safe_rollback(session)
        _log_audit_write_failure(
            error=exc,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=current_user_id,
            policy=AUDIT_POLICY_SECURITY_CRITICAL,
        )
        raise SecurityAuditWriteError(
            f"Security-critical audit commit failed for action={action!r}."
        ) from exc


async def _persist_http_audit_log(
    *,
    actor: _AuditActor | None,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    ip: str | None,
) -> None:
    session = None
    try:
        async with AsyncSessionFactory() as session:
            await _stage_audit_log(
                session,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip=ip,
            )
            await session.commit()
    except Exception as exc:
        if session is not None:
            await _safe_rollback(session)
        _log_audit_write_failure(
            error=exc,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=actor.user_id if actor else None,
            policy=AUDIT_POLICY_OPERATIONAL,
        )


class AuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        actor_token = _request_audit_actor.set(None)
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            if method == "GET" or path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
                await self.app(scope, receive, send_wrapper)
                return

            await self.app(scope, receive, send_wrapper)

            if status_code is None or status_code < 200 or status_code >= 300:
                return

            action, resource_type, resource_id = _classify(method, path)
            actor = _audit_actor_from_scope(scope)
            if actor is None:
                auth_header = Headers(scope=scope).get("authorization")
                user_id, impersonated_by = _decode_user(auth_header)
                actor = _AuditActor(
                    user_id=user_id,
                    user_email=None,
                    org_id=None,
                    impersonated_by=impersonated_by,
                )

            client = scope.get("client")
            ip = client[0] if client else None
            await _persist_http_audit_log(
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip=ip,
            )
        finally:
            _request_audit_actor.reset(actor_token)
