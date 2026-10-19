"""FastAPI DI providery modulu catalog."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_redis
from app.platform.db.session import get_db_session
from app.modules.catalog.material_catalog_repository import MaterialCatalogRepository
from app.modules.catalog.pricebook_repository import PricebookRepository
from app.modules.catalog.supplier_repository import SupplierRepository
from app.modules.catalog.work_catalog_repository import WorkCatalogRepository
from app.modules.catalog.material_catalog_service import MaterialCatalogService
from app.modules.catalog.pricebook_service import PricebookService
from app.modules.catalog.supplier_service import SupplierService
from app.modules.catalog.work_catalog_service import WorkCatalogService


def get_pricebook_service(session: AsyncSession = Depends(get_db_session)) -> PricebookService:
    return PricebookService(PricebookRepository(session))


def get_material_catalog_service(session: AsyncSession = Depends(get_db_session)) -> MaterialCatalogService:
    return MaterialCatalogService(MaterialCatalogRepository(session))


def get_supplier_service(session: AsyncSession = Depends(get_db_session)) -> SupplierService:
    return SupplierService(SupplierRepository(session))


def get_work_catalog_service(
    session: AsyncSession = Depends(get_db_session),
    redis=Depends(get_redis),
) -> WorkCatalogService:
    return WorkCatalogService(WorkCatalogRepository(session), redis=redis)
