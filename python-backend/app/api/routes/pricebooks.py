from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, get_pricebook_service, get_redis, require_org_id
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.cache import delete_cached, get_cache_tag, get_cached, invalidate_cache_tag, set_cached
from app.core.tenant_timing import (
    TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
    enforce_timing_floor,
)
from app.schemas.auth import AuthUserRead
from app.schemas.pricebook import PricebookCreate, PricebookItemRead, PricebookListResponse, PricebookRead
from app.services.pricebook_service import PricebookService
from app.work_catalog.cache import pricing_resolution_cache_scope

router = APIRouter(tags=["pricebooks"])

# R-32: pricebooks change infrequently — 5-minute cache is safe
_LIST_TTL = 300


def _list_key(org_id: str) -> str:
    return f"pricebooks:list:{org_id}"


def _list_scope(org_id: str) -> str:
    return f"pricebooks:{org_id}"


async def _list_pricebooks_core(
    current_user: AuthUserRead,
    service: PricebookService,
    redis,
) -> PricebookListResponse:
    """Pure application logic: org guard, cache lookup, DB fallback.

    No Request dependency — directly testable without framework context.
    """
    started_at = perf_counter()
    try:
        org_id = require_org_id(current_user)
        cache_tag = await get_cache_tag(redis, _list_scope(org_id))
        cached = await get_cached(redis, _list_key(org_id), tag=cache_tag)
        if cached is not None:
            return PricebookListResponse(items=[PricebookRead.model_validate(i) for i in cached])

        items = await service.list_pricebooks(org_id)
        await set_cached(
            redis,
            _list_key(org_id),
            [i.model_dump(mode="json") for i in items],
            _LIST_TTL,
            tag=cache_tag,
        )
        return PricebookListResponse(items=items)
    finally:
        await enforce_timing_floor(
            started_at,
            minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
        )


@router.get("/pricebooks", response_model=PricebookListResponse)
@limiter.limit(get_settings().rate_limit_read_list)
async def list_pricebooks(
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
    redis=Depends(get_redis),
) -> PricebookListResponse:
    return await _list_pricebooks_core(current_user=current_user, service=service, redis=redis)


@router.post("/pricebooks", response_model=PricebookRead, status_code=status.HTTP_201_CREATED)
async def create_pricebook(
    payload: PricebookCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
    redis=Depends(get_redis),
) -> PricebookRead:
    org_id = require_org_id(current_user)
    result = await service.create_pricebook(payload, org_id)
    # Invalidate list cache so the next GET reflects the new pricebook
    await invalidate_cache_tag(redis, _list_scope(org_id))
    await invalidate_cache_tag(redis, pricing_resolution_cache_scope(org_id))
    await delete_cached(redis, _list_key(org_id))
    return result


@router.get("/pricebooks/{pricebook_id}/items", response_model=list[PricebookItemRead])
@limiter.limit(get_settings().rate_limit_read_list)
async def list_pricebook_items(
    pricebook_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
) -> list[PricebookItemRead]:
    started_at = perf_counter()
    try:
        org_id = require_org_id(current_user)
        items = await service.list_pricebook_items(pricebook_id, org_id)
        if items is None:
            raise HTTPException(status_code=404, detail="Pricebook not found.")
        return items
    finally:
        await enforce_timing_floor(
            started_at,
            minimum_seconds=TENANT_SENSITIVE_TIMING_FLOOR_SECONDS,
        )
