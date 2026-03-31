from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_analysis_service,
    get_current_user,
    get_job_queue,
    get_project_service,
    get_quote_variant_service,
    require_manager,
    resolve_org_id,
)
from app.schemas.auth import AuthUserRead
from app.schemas.quote_variant import QuoteVariantListResponse, QuoteVariantRecalculateResponse
from app.services.analysis_service import AnalysisService
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


@router.post(
    "/cases/{case_id}/estimates/recalculate",
    response_model=QuoteVariantRecalculateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def recalculate_case_estimates(
    case_id: str,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    quote_service: QuoteVariantService = Depends(get_quote_variant_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    job_queue=Depends(get_job_queue),
) -> QuoteVariantRecalculateResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")

    if not await quote_service.can_recalculate_quote_variants(case_id):
        raise HTTPException(status_code=400, detail="Estimates cannot be recalculated without an analysis result.")

    create_result = await analysis_service.enqueue_quote_recalculation_job(
        project_id=case_id,
        organization_id=org_id,
        requested_by_user_id=current_user.id,
        parent_job_id=None,
        job_queue=job_queue,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    return QuoteVariantRecalculateResponse(
        variants=[],
        jobId=create_result.job.id,
        jobStatus=create_result.job.status,
        jobType=create_result.job.job_type,
        createdNew=create_result.created_new,
    )
