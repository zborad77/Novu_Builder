"""FastAPI DI providery modulu quoting."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_redis
from app.platform.db.session import get_db_session
from app.modules.quoting.quote_variant_repository import QuoteVariantRepository
from app.modules.catalog.public import WorkCatalogRepository
from app.modules.quoting.quote_variant_service import QuoteVariantService


def get_quote_variant_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> QuoteVariantService:
    return QuoteVariantService(
        QuoteVariantRepository(session),
        WorkCatalogRepository(session),
        redis=redis,
    )
