from fastapi import Depends, Header, HTTPException
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


async def require_manager(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    """Manager nebo superadmin. Technician nemá přístup."""
    if current_user.role not in ("manager", "superadmin") and not current_user.isSuperAdmin:
        raise HTTPException(status_code=403, detail="Manager access required.")
    return current_user


def get_export_service() -> ExportService:
    return ExportService()
