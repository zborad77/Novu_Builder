from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, get_redis, get_supplier_service, require_org_id
from app.core.cache import delete_cached, get_cache_tag, get_cached, invalidate_cache_tag, set_cached
from app.core.tenant_timing import (
    TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
    enforce_timing_floor,
)
from app.schemas.auth import AuthUserRead
from app.schemas.supplier import SupplierPatch
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

ALLOWED_INTEGRATION_TYPES = {"manual", "csv_import", "api", "partner_feed"}

# R-32: suppliers are read-heavy catalog data; 60s TTL with explicit invalidation on PATCH
_LIST_TTL = 60


def _list_key(org_id: str, include_inactive: bool) -> str:
    return f"suppliers:list:{org_id}:{include_inactive}"


def _list_scope(org_id: str) -> str:
    return f"suppliers:{org_id}"


@router.get("")
async def list_suppliers(
    includeInactive: bool = Query(default=False),
    current_user: AuthUserRead = Depends(get_current_user),
    service: SupplierService = Depends(get_supplier_service),
    redis=Depends(get_redis),
):
    started_at = perf_counter()
    try:
        org_id = require_org_id(current_user)
        cache_key = _list_key(org_id, includeInactive)
        cache_tag = await get_cache_tag(redis, _list_scope(org_id))
        cached = await get_cached(redis, cache_key, tag=cache_tag)
        if cached is not None:
            return cached  # already {"items": [...], "total": N}

        items = await service.list_suppliers(org_id, include_inactive=includeInactive)
        result = {"items": [item.model_dump(mode="json") for item in items], "total": len(items)}
        await set_cached(redis, _list_key(org_id, includeInactive), result, _LIST_TTL, tag=cache_tag)
        return result
    finally:
        await enforce_timing_floor(
            started_at,
            minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
        )


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
    org_id = require_org_id(current_user)
    updated = await service.update_supplier(
        supplier_id,
        org_id,
        name=payload.name.strip(),
        website_url=payload.websiteUrl.strip() if isinstance(payload.websiteUrl, str) and payload.websiteUrl.strip() else None,
        integration_type=payload.integrationType,
        contact_name=payload.contactName.strip() if isinstance(payload.contactName, str) and payload.contactName.strip() else None,
        contact_email=payload.contactEmail.strip() if isinstance(payload.contactEmail, str) and payload.contactEmail.strip() else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    # Invalidate both active-only and all-suppliers variants
    await invalidate_cache_tag(redis, _list_scope(org_id))
    await delete_cached(
        redis,
        _list_key(org_id, False),
        _list_key(org_id, True),
    )
    return updated.model_dump()
