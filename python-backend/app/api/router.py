from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.routes.admin import router as admin_router
from app.api.routes.analysis_jobs import router as analysis_jobs_router
from app.api.routes.auth import router as auth_router
from app.api.routes.case_events import router as case_events_router
from app.api.routes.cases import router as cases_router
from app.api.routes.estimates import router as estimates_router
from app.api.routes.exports import router as exports_router
from app.api.routes.images import router as images_router
from app.api.routes.markers import router as markers_router
from app.api.routes.material_catalog import router as material_catalog_router
from app.api.routes.measurements import router as measurements_router
from app.api.routes.pricebooks import router as pricebooks_router
from app.api.routes.suppliers import router as suppliers_router
from app.api.routes.system import router as system_router
from app.api.routes.offer_events import router as offer_events_router
from app.api.routes.offer_requests import router as offer_requests_router
from app.api.routes.work_catalog import router as work_catalog_router

# Canonical API uses the /cases/* surface shared by the current clients.
# Legacy /projects/* aliases are not registered in this package anymore, so
# new route wiring should stay anchored here to avoid drift.

_protected = {"dependencies": [Depends(get_current_user)]}

api_router = APIRouter()
# Public - no auth required
api_router.include_router(system_router, tags=["system"])
api_router.include_router(auth_router)
# Protected - valid JWT required on all routes below
api_router.include_router(cases_router, dependencies=_protected["dependencies"])
api_router.include_router(case_events_router, dependencies=_protected["dependencies"])
api_router.include_router(images_router, dependencies=_protected["dependencies"])
api_router.include_router(analysis_jobs_router, dependencies=_protected["dependencies"])
api_router.include_router(markers_router, dependencies=_protected["dependencies"])
api_router.include_router(measurements_router, dependencies=_protected["dependencies"])
api_router.include_router(estimates_router, dependencies=_protected["dependencies"])
api_router.include_router(pricebooks_router, dependencies=_protected["dependencies"])
api_router.include_router(exports_router, dependencies=_protected["dependencies"])
api_router.include_router(material_catalog_router, dependencies=_protected["dependencies"])
api_router.include_router(suppliers_router, dependencies=_protected["dependencies"])
api_router.include_router(work_catalog_router, dependencies=_protected["dependencies"])
api_router.include_router(admin_router, dependencies=_protected["dependencies"])
api_router.include_router(offer_requests_router, dependencies=_protected["dependencies"])
api_router.include_router(offer_events_router, dependencies=_protected["dependencies"])
