from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_redis, get_supplier_service
from app.core.cache import delete_cached, get_cached, set_cached
from app.schemas.auth import AuthUserRead
from app.schemas.supplier import SupplierPatch
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

ALLOWED_INTEGRATION_TYPES = {"manual", "csv_import", "api", "partner_feed"}

# R-32: suppliers are read-heavy catalog data; 60s TTL with explicit invalidation on PATCH
_LIST_TTL = 60


def _list_key(org_id: str, include_inactive: bool) -> str:
    return f"suppliers:list:{org_id}:{include_inactive}"


@router.get("")
async def list_suppliers(
    includeInactive: bool = Query(default=False),
    current_user: AuthUserRead = Depends(get_current_user),
    service: SupplierService = Depends(get_supplier_service),
    redis=Depends(get_redis),
):
    org_id = current_user.organizationId
    # R-32: only cache tenant-scoped views; superadmin (org_id=None) bypasses cache
    if org_id:
        cache_key = _list_key(org_id, includeInactive)
        cached = await get_cached(redis, cache_key)
        if cached is not None:
            return cached  # already {"items": [...], "total": N}

    items = await service.list_suppliers(org_id, include_inactive=includeInactive)
    result = {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}

    if org_id:
        await set_cached(redis, _list_key(org_id, includeInactive), result, _LIST_TTL)
    return result


@router.patch("/{supplier_id}")
async def patch_supplier(
    supplier_id: str,
    payload: SupplierPatch,
    current_user: AuthUserRead = Depends(get_current_user),
    service: SupplierService = Depends(get_supplier_service),
    redis=Depends(get_redis),
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
    # Invalidate both active-only and all-suppliers variants
    if current_user.organizationId:
        await delete_cached(
            redis,
            _list_key(current_user.organizationId, False),
            _list_key(current_user.organizationId, True),
        )
    return updated.model_dump()
