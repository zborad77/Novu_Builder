"""FastAPI DI providery modulu analysis."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_redis
from app.platform.config import get_settings
from app.platform.db.session import get_db_session
from app.modules.analysis.analysis_repository import AnalysisRepository
from app.modules.media.photo_repository import PhotoRepository
from app.modules.catalog.work_catalog_repository import WorkCatalogRepository
from app.modules.analysis.analysis_service import AnalysisService


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
