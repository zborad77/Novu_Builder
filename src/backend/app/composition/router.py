from fastapi import APIRouter, Depends

from app.composition.deps import get_current_user
from app.modules.admin.api.admin import router as admin_router
from app.modules.analysis.api.analysis_jobs import router as analysis_jobs_router
from app.modules.identity.api.auth import router as auth_router
from app.modules.workflow.api.case_events import router as case_events_router
from app.modules.workflow.api.cases import router as cases_router
from app.modules.quoting.api.estimates import router as estimates_router
from app.modules.exports.api.exports import router as exports_router
from app.modules.media.api.images import router as images_router
from app.modules.media.api.markers import router as markers_router
from app.modules.catalog.api.material_catalog import router as material_catalog_router
from app.modules.analysis.api.measurements import router as measurements_router
from app.modules.catalog.api.pricebooks import router as pricebooks_router
from app.modules.catalog.api.suppliers import router as suppliers_router
from app.composition.api.system import router as system_router
from app.modules.offers.api.offer_events import router as offer_events_router
from app.modules.offers.api.offer_requests import router as offer_requests_router
from app.modules.identity.api.org_users import router as org_users_router
from app.modules.catalog.api.work_catalog import router as work_catalog_router

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
# D-10: firemní admin spravuje uživatele vlastní firmy (zóny gateway a desktop).
api_router.include_router(org_users_router, dependencies=_protected["dependencies"])
api_router.include_router(offer_requests_router, dependencies=_protected["dependencies"])
api_router.include_router(offer_events_router, dependencies=_protected["dependencies"])
