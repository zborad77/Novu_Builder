from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.routes.auth import router as auth_router
from app.api.routes.analysis_jobs import router as analysis_jobs_router
from app.api.routes.cases import router as cases_router
from app.api.routes.estimates import router as estimates_router
from app.api.routes.exports import router as exports_router
from app.api.routes.images import router as images_router
from app.api.routes.material_catalog import router as material_catalog_router
from app.api.routes.measurements import router as measurements_router
from app.api.routes.pricebooks import router as pricebooks_router
from app.api.routes.suppliers import router as suppliers_router
from app.api.routes.system import router as system_router

# Canonical API uses /cases/* prefix (matches desktop Qt client).
# The following routers exist as files but are not registered — they duplicate
# the above routes under a /projects/* prefix and are kept for reference only:
#   projects.py, photos.py, analysis.py, quote_variants.py

_protected = {"dependencies": [Depends(get_current_user)]}

api_router = APIRouter()
# Public — no auth required
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router)
# Protected — valid JWT required on all routes below
api_router.include_router(cases_router, **_protected)
api_router.include_router(images_router, **_protected)
api_router.include_router(analysis_jobs_router, **_protected)
api_router.include_router(measurements_router, **_protected)
api_router.include_router(estimates_router, **_protected)
api_router.include_router(pricebooks_router, **_protected)
api_router.include_router(exports_router, **_protected)
api_router.include_router(material_catalog_router, **_protected)
api_router.include_router(suppliers_router, **_protected)
