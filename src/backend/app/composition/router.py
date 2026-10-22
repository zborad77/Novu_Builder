from fastapi import APIRouter, Depends

from app.modules.identity.public import get_current_user
from app.modules.admin.public import admin_router
from app.modules.analysis.public import analysis_jobs_router
from app.modules.identity.public import auth_router
from app.modules.workflow.public import case_events_router
from app.modules.workflow.public import cases_router
from app.modules.quoting.public import estimates_router
from app.modules.exports.public import exports_router
from app.modules.media.public import images_router
from app.modules.media.public import image_files_router
from app.modules.exports.public import export_files_router
from app.modules.identity.public import internal_security_events_router
from app.modules.media.public import markers_router
from app.modules.catalog.public import material_catalog_router
from app.modules.analysis.public import measurements_router
from app.modules.catalog.public import pricebooks_router
from app.modules.catalog.public import suppliers_router
from app.composition.api.system import router as system_router
from app.modules.offers.public import offer_events_router
from app.modules.offers.public import offer_requests_router
from app.modules.identity.public import org_users_router
from app.modules.catalog.public import work_catalog_router

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
# NC-007 kap. 6 (aditivně, na konec – pořadí stávajících rout se nemění):
# streamování fotek a exportů (zóny gateway a desktop, JWT povinné) ...
api_router.include_router(image_files_router, dependencies=_protected["dependencies"])
api_router.include_router(export_files_router, dependencies=_protected["dependencies"])
# ... a interní příjem bezpečnostních událostí z gateway (jen zóna gateway, podpis
# gateway; JWT se NEPOUŽÍVÁ – požadavek s Authorization dostane 404).
api_router.include_router(internal_security_events_router)
