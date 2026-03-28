from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.analysis_repository import AnalysisRepository
from app.db.session import get_db_session
from app.schemas.auth import AuthUserRead
from app.repositories.final_proposal_repository import FinalProposalRepository
from app.repositories.material_catalog_repository import MaterialCatalogRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.pricebook_repository import PricebookRepository
from app.repositories.proposal_draft_repository import ProposalDraftRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.quote_variant_repository import QuoteVariantRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService
from app.services.export_service import ExportService
from app.services.material_catalog_service import MaterialCatalogService
from app.services.photo_service import PhotoService
from app.services.pricebook_service import PricebookService
from app.services.project_service import ProjectService
from app.services.quote_variant_service import QuoteVariantService
from app.services.supplier_service import SupplierService


def get_project_service(session: AsyncSession = Depends(get_db_session)) -> ProjectService:
    return ProjectService(
        ProjectRepository(session),
        ProposalDraftRepository(session),
        FinalProposalRepository(session),
        ExportService(),
    )


def get_photo_service(session: AsyncSession = Depends(get_db_session)) -> PhotoService:
    repository = PhotoRepository(session)
    return PhotoService(repository)


def get_analysis_service(session: AsyncSession = Depends(get_db_session)) -> AnalysisService:
    settings = get_settings()
    return AnalysisService(
        repository=AnalysisRepository(session),
        photo_repository=PhotoRepository(session),
        provider_key=settings.ai_analysis_provider,
    )


def get_quote_variant_service(session: AsyncSession = Depends(get_db_session)) -> QuoteVariantService:
    return QuoteVariantService(QuoteVariantRepository(session))


def get_pricebook_service(session: AsyncSession = Depends(get_db_session)) -> PricebookService:
    return PricebookService(PricebookRepository(session))


def get_material_catalog_service(session: AsyncSession = Depends(get_db_session)) -> MaterialCatalogService:
    return MaterialCatalogService(MaterialCatalogRepository(session))


def get_supplier_service(session: AsyncSession = Depends(get_db_session)) -> SupplierService:
    return SupplierService(SupplierRepository(session))


def get_auth_service(session: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(session)


async def get_current_user(
    authorization: str = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUserRead:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")
    token = authorization[7:]
    user = await auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return user


async def require_superadmin(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    if not current_user.isSuperAdmin:
        raise HTTPException(status_code=403, detail="Super-admin access required.")
    if current_user.impersonatedBy:
        raise HTTPException(status_code=403, detail="Impersonated tokens cannot access admin routes.")
    return current_user


# ── Granular RBAC foundation ────────────────────────────────────────────────────
#
# All capabilities currently map to superadmin-only. When per-role permissions
# are introduced (e.g. from a DB permission table), extend _check() here without
# changing any route signature.

ADMIN_CAPABILITIES: frozenset[str] = frozenset({
    "admin:read",
    "admin:write",
    "admin:jobs",
    "admin:impersonate",
})


def require_admin_capability(capability: str):
    """Return a FastAPI dependency that enforces the given admin capability.

    C8: checks the role_permissions table so non-superadmin roles (e.g. manager)
    can be granted specific capabilities without becoming full superadmin.

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
            raise HTTPException(status_code=403, detail="Impersonated tokens cannot access admin routes.")

        # Superadmin always has all capabilities
        if current_user.isSuperAdmin:
            return current_user

        # Check DB-backed role permission
        from sqlalchemy import select as _select
        from app.models import RolePermission
        result = await session.execute(
            _select(RolePermission).where(
                RolePermission.role == current_user.role,
                RolePermission.capability == capability,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail=f"Permission denied: {capability!r} required.")

        return current_user

    _check.__name__ = f"require_{capability.replace(':', '_')}"
    return _check


def resolve_org_id(current_user: AuthUserRead) -> str | None:
    """Return the effective organization_id for tenant-scoped queries.

    Superadmin → None (intentional cross-tenant bypass, logged at service layer).
    Regular user → their organizationId.
    Fail-fast if a non-superadmin user somehow has no organizationId set — this
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


async def require_manager(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    """Manager nebo superadmin. Technician nemá přístup."""
    if current_user.role not in ("manager", "superadmin") and not current_user.isSuperAdmin:
        raise HTTPException(status_code=403, detail="Manager access required.")
    return current_user


def get_export_service() -> ExportService:
    return ExportService()


def get_job_queue(request: Request):
    """Return the Redis job queue from app state, or None if unavailable."""
    return getattr(request.app.state, "job_queue", None)


def get_redis(request: Request):
    """Return the shared Redis client for caching (R-32), or None if unavailable.

    Reuses the same connection as the job queue — key prefixes keep them isolated:
      job queue: analysis:jobs
      cache:     cache:*
    """
    return getattr(request.app.state, "job_queue", None)
