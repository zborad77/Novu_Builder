from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_project_service, get_quote_variant_service
from app.schemas.quote_variant import AnalysisJobRead, QuoteVariantListResponse, QuoteVariantPatch, QuoteVariantRead, QuoteVariantRecalculateResponse
from app.services.project_service import ProjectService
from app.services.quote_variant_service import QuoteVariantService

router = APIRouter(tags=["quote-variants"])


@router.get("/analysis-jobs/{job_id}", response_model=AnalysisJobRead)
async def get_analysis_job(
    job_id: str,
    service: QuoteVariantService = Depends(get_quote_variant_service),
) -> AnalysisJobRead:
    job = await service.get_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job


@router.get("/projects/{project_id}/quote-variants", response_model=QuoteVariantListResponse)
async def list_quote_variants(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    service: QuoteVariantService = Depends(get_quote_variant_service),
) -> QuoteVariantListResponse:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    items = await service.list_quote_variants(project_id)
    return QuoteVariantListResponse(items=items)


@router.post("/projects/{project_id}/quote-variants/recalculate", response_model=QuoteVariantRecalculateResponse)
async def recalculate_quote_variants(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    service: QuoteVariantService = Depends(get_quote_variant_service),
) -> QuoteVariantRecalculateResponse:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    variants = await service.recalculate_quote_variants(project_id)
    if variants is None:
        raise HTTPException(status_code=400, detail="Quote variants cannot be recalculated without an analysis result.")

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


@router.patch("/quote-variants/{variant_id}", response_model=QuoteVariantRead)
async def patch_quote_variant(
    variant_id: str,
    payload: QuoteVariantPatch,
    service: QuoteVariantService = Depends(get_quote_variant_service),
) -> QuoteVariantRead:
    updated = await service.update_quote_variant(
        variant_id,
        payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Quote variant not found.")
    return updated
