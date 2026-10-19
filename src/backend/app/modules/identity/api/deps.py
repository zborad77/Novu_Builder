"""Autentizace a autorizace požadavku: aktuální uživatel, RBAC guardy, tenant (org_id)."""

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import structlog.contextvars

from app.platform.http.deps import get_auth_redis
from app.modules.audit.public import bind_request_audit_actor
from app.modules.identity.device_binding import check_device_binding
from app.modules.identity.rbac import is_system_admin, is_tenant_admin, is_tenant_operator
from app.platform.db.session import get_db_session
from app.modules.identity.token_repository import TokenStateBackendUnavailableError
from app.modules.identity.schemas.auth import AuthUserRead
from app.modules.identity.auth_service import AuthService
from app.modules.identity.company_service import CompanyService


logger = structlog.get_logger(__name__)


def get_auth_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_auth_redis),
) -> AuthService:
    return AuthService(session, redis=redis)


async def get_current_user(
    request: Request,
    authorization: str = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUserRead:
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning(
            "SECURITY_EVENT: auth_header_invalid",
            reason="missing_or_invalid_bearer_header",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization[7:]
    try:
        user = await auth_service.get_user_by_token(token)
    except TokenStateBackendUnavailableError as exc:
        logger.error(
            "SECURITY_EVENT: auth_token_validation_unavailable",
            operation=exc.operation,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
            error=str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail="Authentication token validation unavailable. Retry later.",
        ) from exc
    if not user:
        logger.warning(
            "SECURITY_EVENT: token_rejected",
            reason="invalid_or_expired_token",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    # F3.6: in the desktop zone the device (WireGuard address) must belong to the user's company.
    if check_device_binding(request.client.host if request.client else None, user.organizationId) != "allow":
        raise HTTPException(status_code=403, detail="This device is not authorized for your organization.")
    bind_request_audit_actor(request, user)
    structlog.contextvars.bind_contextvars(
        tenant_id=str(user.organizationId) if user.organizationId else "superadmin",
        user_id=str(user.id),
    )
    return user


async def require_superadmin(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    if not current_user.isSuperAdmin:
        logger.warning(
            "SECURITY_EVENT: superadmin_access_denied",
            user_id=current_user.id,
            role=current_user.role,
        )
        raise HTTPException(status_code=403, detail="Super-admin access required.")
    if current_user.impersonatedBy:
        logger.warning(
            "SECURITY_EVENT: impersonated_admin_access_denied",
            user_id=current_user.id,
            impersonated_by=current_user.impersonatedBy,
        )
        raise HTTPException(status_code=403, detail="Impersonated tokens cannot access admin routes.")
    return current_user


# System (platform) capabilities.
#
# These are held exclusively by superadmins. The role_permissions table is no
# longer consulted: its historical manager rows granted cross-tenant platform
# administration (SA-01) and migration 20261017_0057 removes them. Tenant-level
# administration uses require_user_admin / app.modules.identity.rbac instead.
ADMIN_CAPABILITIES: frozenset[str] = frozenset({
    "admin:read",
    "admin:write",
    "admin:jobs",
    "admin:impersonate",
})


def require_admin_capability(capability: str):
    """Return a FastAPI dependency that enforces the given system capability.

    Deny by default: only a superadmin acting as themselves passes.
    Impersonated tokens are never allowed on admin routes.
    """
    if capability not in ADMIN_CAPABILITIES:
        raise ValueError(f"Unknown admin capability: {capability!r}")

    async def _check(
        current_user: AuthUserRead = Depends(get_current_user),
    ) -> AuthUserRead:
        if current_user.impersonatedBy:
            logger.warning(
                "SECURITY_EVENT: impersonated_admin_access_denied",
                user_id=current_user.id,
                impersonated_by=current_user.impersonatedBy,
                capability=capability,
            )
            raise HTTPException(status_code=403, detail="Impersonated tokens cannot access admin routes.")

        if current_user.isSuperAdmin:
            return current_user

        logger.warning(
            "SECURITY_EVENT: admin_capability_denied",
            user_id=current_user.id,
            role=current_user.role,
            capability=capability,
        )
        raise HTTPException(status_code=403, detail=f"Permission denied: {capability!r} required.")

    _check.__name__ = f"require_{capability.replace(':', '_')}"
    return _check


async def require_user_admin(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    """Superadmin (all tenants) or company admin (own tenant only).

    Which targets the caller may touch is decided per request by app.modules.identity.rbac;
    this dependency only rejects callers with no administration role at all.
    """
    if current_user.impersonatedBy:
        logger.warning(
            "SECURITY_EVENT: impersonated_admin_access_denied",
            user_id=current_user.id,
            impersonated_by=current_user.impersonatedBy,
        )
        raise HTTPException(status_code=403, detail="Impersonated tokens cannot access admin routes.")
    if is_system_admin(current_user) or is_tenant_admin(current_user):
        return current_user
    logger.warning(
        "SECURITY_EVENT: user_admin_access_denied",
        user_id=current_user.id,
        role=current_user.role,
    )
    raise HTTPException(status_code=403, detail="Administrator access required.")


def resolve_org_id(current_user: AuthUserRead) -> str | None:
    """Return the effective organization_id for tenant-scoped queries.

    Superadmin -> None (intentional cross-tenant bypass, logged at service layer).
    Regular user -> their organizationId.
    Fail fast if a non-superadmin user somehow has no organizationId set. This
    prevents an accidental tenant-isolation bypass caused by a misconfigured user.
    """
    if current_user.isSuperAdmin:
        return None
    if not current_user.organizationId:
        raise HTTPException(
            status_code=403,
            detail="User has no organization assigned.",
        )
    return current_user.organizationId


def require_org_id(current_user: AuthUserRead) -> str:
    org_id = resolve_org_id(current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant-scoped route requires an organization context.",
        )
    return org_id


async def require_manager(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    """Company admin, manager or superadmin. Technician access is not allowed.

    Superadmin is recognised by the users.is_superadmin flag, never by the role
    string alone.
    """
    if not is_tenant_operator(current_user):
        raise HTTPException(status_code=403, detail="Manager access required.")
    return current_user


def get_company_service(session: AsyncSession = Depends(get_db_session)) -> CompanyService:
    return CompanyService(session)
