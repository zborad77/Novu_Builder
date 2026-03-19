from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.analysis_repository import AnalysisRepository
from app.db.session import get_db_session
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


def get_auth_service() -> AuthService:
    return AuthService()


def get_export_service() -> ExportService:
    return ExportService()
