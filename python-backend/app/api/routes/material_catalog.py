from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_material_catalog_service
from app.schemas.material_catalog import MaterialCatalogPatch
from app.services.material_catalog_service import MaterialCatalogService

router = APIRouter(prefix="/material-catalog", tags=["material-catalog"])


@router.get("")
async def list_material_catalog(
    search: str | None = Query(default=None),
    includeInactive: bool = Query(default=False),
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    items = await service.list_material_catalog(search=search, include_inactive=includeInactive)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.get("/{material_id}/supplier-prices")
async def list_supplier_prices(
    material_id: str,
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    items = await service.list_supplier_prices(material_id)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.patch("/{material_id}")
async def patch_material(
    material_id: str,
    payload: MaterialCatalogPatch,
    service: MaterialCatalogService = Depends(get_material_catalog_service),
):
    updated = await service.update_material(
        material_id,
        default_unit_price=payload.defaultUnitPrice,
        default_supplier_id=payload.defaultSupplierId,
        notes=payload.notes.strip() if isinstance(payload.notes, str) else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Material not found.")
    return updated.model_dump()
