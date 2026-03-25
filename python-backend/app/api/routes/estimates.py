from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_project_service, get_quote_variant_service, require_manager, resolve_org_id
from app.schemas.auth import AuthUserRead
from app.schemas.quote_variant import QuoteVariantListResponse, QuoteVariantRecalculateResponse
from app.services.project_service import ProjectService
from app.services.quote_variant_service import QuoteVariantService

router = APIRouter(tags=["estimates"])


@router.get("/cases/{case_id}/estimates", response_model=QuoteVariantListResponse)
async def list_case_estimates(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    quote_service: QuoteVariantService = Depends(get_quote_variant_service),
) -> QuoteVariantListResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    items = await quote_service.list_quote_variants(case_id)
    return QuoteVariantListResponse(items=items)


@router.post("/cases/{case_id}/estimates/recalculate", response_model=QuoteVariantRecalculateResponse)
async def recalculate_case_estimates(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    quote_service: QuoteVariantService = Depends(get_quote_variant_service),
) -> QuoteVariantRecalculateResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    variants = await quote_service.recalculate_quote_variants(case_id)
    if variants is None:
        raise HTTPException(status_code=400, detail="Estimates cannot be recalculated without an analysis result.")
    return QuoteVariantRecalculateResponse(
        variants=[
            {
                "id": variant.id,
                "variantType": variant.variantType,
                "totalIncVat": variant.totalIncVat,
            }
            for variant in variants
        ]
    )
