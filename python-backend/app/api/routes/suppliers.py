from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_supplier_service
from app.schemas.auth import AuthUserRead
from app.schemas.supplier import SupplierPatch
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

ALLOWED_INTEGRATION_TYPES = {"manual", "csv_import", "api", "partner_feed"}


@router.get("")
async def list_suppliers(
    includeInactive: bool = Query(default=False),
    current_user: AuthUserRead = Depends(get_current_user),
    service: SupplierService = Depends(get_supplier_service),
):
    items = await service.list_suppliers(current_user.organizationId, include_inactive=includeInactive)
    return {"items": [item.model_dump() for item in items], "total": len(items)}


@router.patch("/{supplier_id}")
async def patch_supplier(
    supplier_id: str,
    payload: SupplierPatch,
    current_user: AuthUserRead = Depends(get_current_user),
    service: SupplierService = Depends(get_supplier_service),
):
    if payload.integrationType not in ALLOWED_INTEGRATION_TYPES:
        raise HTTPException(status_code=400, detail="integrationType must be one of: manual, csv_import, api, partner_feed.")
    updated = await service.update_supplier(
        supplier_id,
        current_user.organizationId,
        name=payload.name.strip(),
        website_url=payload.websiteUrl.strip() if isinstance(payload.websiteUrl, str) and payload.websiteUrl.strip() else None,
        integration_type=payload.integrationType,
        contact_name=payload.contactName.strip() if isinstance(payload.contactName, str) and payload.contactName.strip() else None,
        contact_email=payload.contactEmail.strip() if isinstance(payload.contactEmail, str) and payload.contactEmail.strip() else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return updated.model_dump()
