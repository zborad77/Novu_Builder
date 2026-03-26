from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_pricebook_service, get_redis
from app.core.cache import delete_cached, get_cached, set_cached
from app.schemas.auth import AuthUserRead
from app.schemas.pricebook import PricebookCreate, PricebookItemRead, PricebookListResponse, PricebookRead
from app.services.pricebook_service import PricebookService

router = APIRouter(tags=["pricebooks"])

# R-32: pricebooks change infrequently — 5-minute cache is safe
_LIST_TTL = 300


def _list_key(org_id: str) -> str:
    return f"pricebooks:list:{org_id}"


@router.get("/pricebooks", response_model=PricebookListResponse)
async def list_pricebooks(
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
    redis=Depends(get_redis),
) -> PricebookListResponse:
    org_id = current_user.organizationId
    # R-32: only cache tenant-scoped views; superadmin (org_id=None) bypasses cache
    if org_id:
        cached = await get_cached(redis, _list_key(org_id))
        if cached is not None:
            return PricebookListResponse(items=[PricebookRead.model_validate(i) for i in cached])

    items = await service.list_pricebooks(org_id)

    if org_id:
        await set_cached(redis, _list_key(org_id), [i.model_dump(mode="json") for i in items], _LIST_TTL)
    return PricebookListResponse(items=items)


@router.post("/pricebooks", response_model=PricebookRead, status_code=status.HTTP_201_CREATED)
async def create_pricebook(
    payload: PricebookCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
    redis=Depends(get_redis),
) -> PricebookRead:
    result = await service.create_pricebook(payload, current_user.organizationId)
    # Invalidate list cache so the next GET reflects the new pricebook
    if current_user.organizationId:
        await delete_cached(redis, _list_key(current_user.organizationId))
    return result


@router.get("/pricebooks/{pricebook_id}/items", response_model=list[PricebookItemRead])
async def list_pricebook_items(
    pricebook_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: PricebookService = Depends(get_pricebook_service),
) -> list[PricebookItemRead]:
    items = await service.list_pricebook_items(pricebook_id, current_user.organizationId)
    if items is None:
        raise HTTPException(status_code=404, detail="Pricebook not found.")
    return items
