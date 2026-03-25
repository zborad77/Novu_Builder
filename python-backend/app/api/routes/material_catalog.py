from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_material_catalog_service
from app.schemas.auth import AuthUserRead
from app.schemas.material_catalog import MaterialCatalogPatch
from app.services.material_catalog_service import MaterialCatalogService

router = APIRouter(prefix="/material-catalog", tags=["material-catalog"])


@router.get("")
async def list_material_catalog(
    search: str | None = Query(default=None),
    includeInactive: bool = Query(default=False),
    current_user: AuthUserRead = Depends(get_current_user),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    items = await service.list_material_catalog(organization_id=current_user.organizationId, search=search, include_inactive=includeInactive)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.get("/{material_id}/supplier-prices")
async def list_supplier_prices(
    material_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    items = await service.list_supplier_prices(material_id, current_user.organizationId)
    if items is None:
        raise HTTPException(status_code=404, detail="Material not found.")
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.patch("/{material_id}")
async def patch_material(
    material_id: str,
    payload: MaterialCatalogPatch,
    current_user: AuthUserRead = Depends(get_current_user),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    updated = await service.update_material(
        material_id,
        current_user.organizationId,
        default_unit_price=payload.defaultUnitPrice,
        default_supplier_id=payload.defaultSupplierId,
        notes=payload.notes.strip() if isinstance(payload.notes, str) else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Material not found.")
    return updated.model_dump()
