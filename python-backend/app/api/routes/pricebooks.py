from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_pricebook_service
from app.schemas.pricebook import PricebookCreate, PricebookItemRead, PricebookListResponse, PricebookRead
from app.services.pricebook_service import PricebookService

router = APIRouter(tags=["pricebooks"])


@router.get("/pricebooks", response_model=PricebookListResponse)
async def list_pricebooks(
    service: PricebookService = Depends(get_pricebook_service),
) -> PricebookListResponse:
    items = await service.list_pricebooks()
    return PricebookListResponse(items=items)


@router.post("/pricebooks", response_model=PricebookRead, status_code=status.HTTP_201_CREATED)
async def create_pricebook(
    payload: PricebookCreate,
    service: PricebookService = Depends(get_pricebook_service),
) -> PricebookRead:
    return await service.create_pricebook(payload)


@router.get("/pricebooks/{pricebook_id}/items", response_model=list[PricebookItemRead])
async def list_pricebook_items(
    pricebook_id: str,
    service: PricebookService = Depends(get_pricebook_service),
) -> list[PricebookItemRead]:
    items = await service.list_pricebook_items(pricebook_id)
    if items is None:
        raise HTTPException(status_code=404, detail="Pricebook not found.")
    return items
