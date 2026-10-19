from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.identity.api.deps import get_current_user, require_manager, resolve_org_id
from app.modules.catalog.api.deps import get_material_catalog_service
from app.platform.config import get_settings
from app.platform.http.limiter import limiter
from app.modules.identity.schemas.auth import AuthUserRead
from app.modules.catalog.schemas.material_catalog import MaterialCatalogPatch
from app.modules.catalog.material_catalog_service import MaterialCatalogService

router = APIRouter(prefix="/material-catalog", tags=["material-catalog"])


@router.get("")
@limiter.limit(get_settings().rate_limit_read_list)
async def list_material_catalog(
    request: Request,
    search: str | None = Query(default=None),
    includeInactive: bool = Query(default=False),
    current_user: AuthUserRead = Depends(get_current_user),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    # Tenant-scoped routes must resolve the effective org context centrally;
    # do not read current_user.organizationId directly in handlers.
    org_id = resolve_org_id(current_user)
    items = await service.list_material_catalog(organization_id=org_id, search=search, include_inactive=includeInactive)  # type: ignore[arg-type]
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.get("/{material_id}/supplier-prices")
@limiter.limit(get_settings().rate_limit_read_list)
async def list_supplier_prices(
    material_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    org_id = resolve_org_id(current_user)
    items = await service.list_supplier_prices(material_id, org_id)  # type: ignore[arg-type]
    if items is None:
        raise HTTPException(status_code=404, detail="Material not found.")
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.patch("/{material_id}")
async def patch_material(
    material_id: str,
    payload: MaterialCatalogPatch,
    current_user: AuthUserRead = Depends(require_manager),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    org_id = resolve_org_id(current_user)
    updated = await service.update_material(
        material_id,
        org_id,  # type: ignore[arg-type]
        default_unit_price=payload.defaultUnitPrice,
        default_supplier_id=payload.defaultSupplierId,
        notes=payload.notes.strip() if isinstance(payload.notes, str) else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Material not found.")
    return updated.model_dump()
