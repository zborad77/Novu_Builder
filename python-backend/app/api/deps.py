from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import structlog.contextvars

from app.core.audit import bind_request_audit_actor
from app.core.config import get_settings
from app.db.session import get_db_session
from app.case_workflow.case_actions import CaseActionService
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.export_repository import ExportRepository
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.material_catalog_repository import MaterialCatalogRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.pricebook_repository import PricebookRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.repositories.quote_variant_repository import QuoteVariantRepository
from app.repositories.storage_consistency_repository import StorageConsistencyRepository
from app.repositories.supplier_repository import SupplierRepository
from app.repositories.token_repository import TokenStateBackendUnavailableError
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.auth import AuthUserRead
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService
from app.services.export_service import ExportService
from app.services.material_catalog_service import MaterialCatalogService
from app.services.photo_service import PhotoService
from app.services.pricebook_service import PricebookService
from app.services.project_service import ProjectService
from app.services.quote_variant_service import QuoteVariantService
from app.services.storage_consistency_service import StorageConsistencyService
from app.services.supplier_service import SupplierService
from app.services.work_catalog_service import WorkCatalogService

logger = structlog.get_logger(__name__)


def _request_app_state(request: Request):
    """Best-effort access to ASGI app state.

    Route adapter dependencies may run in direct-call tests or narrow harnesses
    where the Request has no bound ``app``. In that case return ``None`` rather
    than failing on framework wiring.
    """
    app = None
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        try:
            app = request.app
        except Exception:
            app = None
    else:
        app = scope.get("app")
        if app is None:
            try:
                app = request.app
            except Exception:
                app = None
    return getattr(app, "state", None)


def get_job_queue(request: Request):
    """Return the Redis job queue from app state, or None if unavailable."""
    state = _request_app_state(request)
    return getattr(state, "job_queue", None)


def get_redis(request: Request):
    """Return the shared Redis client for caching (R-32), or None if unavailable.

    Reuses the same connection as the job queue; key prefixes keep them isolated:
      job queue: analysis:jobs
      cache:     cache:*
    """
    state = _request_app_state(request)
    return getattr(state, "job_queue", None)


def get_auth_redis(request: Request):
    """Return the shared Redis client for auth token-state caching."""
    state = _request_app_state(request)
    auth_store = getattr(state, "auth_token_store", None)
    if auth_store is not None:
        return auth_store
    return getattr(state, "job_queue", None)


def get_project_service(session: AsyncSession = Depends(get_db_session)) -> ProjectService:
    return ProjectService(
        ProjectRepository(session),
        ProposalDraftRepository(session),
        FinalProposalRepository(session),
        ExportService(ExportRepository(session)),
    )


def get_case_action_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> CaseActionService:
    return CaseActionService(ProjectRepository(session), work_queue=work_queue)


def get_photo_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> PhotoService:
    repository = PhotoRepository(session)
    return PhotoService(repository, work_queue=work_queue)


def get_analysis_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> AnalysisService:
    settings = get_settings()
    return AnalysisService(
        repository=AnalysisRepository(session),
        photo_repository=PhotoRepository(session),
        work_catalog_repository=WorkCatalogRepository(session),
        provider_key=settings.ai_analysis_provider,
        redis=redis,
    )


def get_quote_variant_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> QuoteVariantService:
    return QuoteVariantService(
        QuoteVariantRepository(session),
        WorkCatalogRepository(session),
        redis=redis,
    )


def get_pricebook_service(session: AsyncSession = Depends(get_db_session)) -> PricebookService:
    return PricebookService(PricebookRepository(session))


def get_material_catalog_service(session: AsyncSession = Depends(get_db_session)) -> MaterialCatalogService:
    return MaterialCatalogService(MaterialCatalogRepository(session))


def get_supplier_service(session: AsyncSession = Depends(get_db_session)) -> SupplierService:
    return SupplierService(SupplierRepository(session))


def get_storage_consistency_service(
    session: AsyncSession = Depends(get_db_session),
) -> StorageConsistencyService:
    return StorageConsistencyService(StorageConsistencyRepository(session))


def get_work_catalog_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> WorkCatalogService:
    return WorkCatalogService(WorkCatalogRepository(session), redis=redis)


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


# Granular RBAC foundation
#
# All capabilities currently map to superadmin-only. When per-role permissions
# are introduced (for example from a DB permission table), extend _check() here
# without changing any route signature.
ADMIN_CAPABILITIES: frozenset[str] = frozenset({
    "admin:read",
    "admin:write",
    "admin:jobs",
    "admin:impersonate",
})


def require_admin_capability(capability: str):
    """Return a FastAPI dependency that enforces the given admin capability.

    C8: checks the role_permissions table so non-superadmin roles (for example
    manager) can be granted specific capabilities without becoming full
    superadmin.

    Superadmin always has all capabilities (enforced before the DB lookup).
    Impersonated tokens are never allowed on admin routes.
    """
    if capability not in ADMIN_CAPABILITIES:
        raise ValueError(f"Unknown admin capability: {capability!r}")

    async def _check(
        current_user: AuthUserRead = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
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

        from sqlalchemy import select as _select
        from app.models import RolePermission

        result = await session.execute(
            _select(RolePermission).where(
                RolePermission.role == current_user.role,
                RolePermission.capability == capability,
            )
        )
        if result.scalar_one_or_none() is None:
            logger.warning(
                "SECURITY_EVENT: admin_capability_denied",
                user_id=current_user.id,
                role=current_user.role,
                capability=capability,
            )
            raise HTTPException(status_code=403, detail=f"Permission denied: {capability!r} required.")

        return current_user

    _check.__name__ = f"require_{capability.replace(':', '_')}"
    return _check


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
    """Manager or superadmin. Technician access is not allowed."""
    if current_user.role not in ("manager", "superadmin"):
        raise HTTPException(status_code=403, detail="Manager access required.")
    return current_user


def get_export_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> ExportService:
    return ExportService(ExportRepository(session), work_queue=work_queue)
