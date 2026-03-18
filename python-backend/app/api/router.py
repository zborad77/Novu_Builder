from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.analysis_jobs import router as analysis_jobs_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.cases import router as cases_router
from app.api.routes.estimates import router as estimates_router
from app.api.routes.exports import router as exports_router
from app.api.routes.images import router as images_router
from app.api.routes.material_catalog import router as material_catalog_router
from app.api.routes.measurements import router as measurements_router
from app.api.routes.photos import router as photos_router
from app.api.routes.pricebooks import router as pricebooks_router
from app.api.routes.projects import router as projects_router
from app.api.routes.quote_variants import router as quote_variants_router
from app.api.routes.suppliers import router as suppliers_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router)
api_router.include_router(cases_router)
api_router.include_router(images_router)
api_router.include_router(analysis_jobs_router)
api_router.include_router(measurements_router)
api_router.include_router(estimates_router)
api_router.include_router(pricebooks_router)
api_router.include_router(exports_router)
api_router.include_router(material_catalog_router)
api_router.include_router(suppliers_router)
api_router.include_router(projects_router)
api_router.include_router(photos_router)
api_router.include_router(analysis_router)
api_router.include_router(quote_variants_router)
