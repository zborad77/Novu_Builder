import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_analysis_service, get_current_user, get_job_queue, get_project_service, require_manager, resolve_org_id
from app.core.audit import log_cross_tenant_denied
from app.core.config import get_settings
from app.core.limiter import limiter
from app.schemas.analysis import AnalysisJobCreateRequest, AnalysisTriggerResponse
from app.schemas.auth import AuthUserRead
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService
from app.worker.queue import AnalysisJobQueueCapacityExceededError, enqueue_analysis_job

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["analysis-jobs"])


@router.post("/cases/{case_id}/analysis-jobs", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().rate_limit_analysis_jobs)
async def create_analysis_job(
    case_id: str,
    request: Request,
    body: AnalysisJobCreateRequest | None = None,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    job_queue=Depends(get_job_queue),
) -> AnalysisTriggerResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    settings = get_settings()
    create_result = await analysis_service.create_job(
        project,
        user_id=current_user.id,
        job_queue=job_queue,
        work_type_code=body.workTypeCode if body else None,
    )
    job = create_result.job
    if job_queue is not None and create_result.created_new:
        try:
            await enqueue_analysis_job(
                job_queue,
                job_id=job.id,
                project_id=case_id,
                organization_id=org_id,
                is_superadmin_context=current_user.isSuperAdmin,
                max_depth=settings.analysis_queue_max_depth,
            )
        except AnalysisJobQueueCapacityExceededError:
            await analysis_service.cancel_analysis_job(job.id, organization_id=org_id)
            raise HTTPException(status_code=429, detail="Analysis queue is full. Please retry later.")
    elif job_queue is not None:
        logger.info("job_queue.skip_duplicate_enqueue", job_id=job.id, action="create_analysis_job")
    else:
        logger.warning("job_queue.unavailable", job_id=job.id, action="create_analysis_job")
    return AnalysisTriggerResponse(
        jobId=job.id,
        status=job.status,
        workTypeCode=getattr(job, "requested_work_type_code", None),
        analysisProfileCode=getattr(job, "resolved_analysis_profile_code", None),
        analysisProfileVersion=getattr(job, "resolved_analysis_profile_version", None),
        provider=analysis_service.provider_key,
    )


@router.get("/cases/{case_id}/analysis-jobs", response_model=list[dict])
async def list_case_analysis_jobs(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> list[dict]:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    return await analysis_service.list_jobs(case_id)


@router.get("/analysis-jobs/{job_id}", response_model=dict)
async def get_analysis_job(
    job_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> dict:
    org_id = resolve_org_id(current_user)
    job = await analysis_service.get_job(job_id, organization_id=org_id)
    if not job:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="analysis_job", resource_id=job_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job


@router.post("/analysis-jobs/{job_id}/cancel", response_model=dict)
async def cancel_analysis_job(
    job_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> dict:
    org_id = resolve_org_id(current_user)
    updated = await analysis_service.cancel_analysis_job(job_id, organization_id=org_id)
    if not updated:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="analysis_job_cancel", resource_id=job_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return updated


@router.patch("/cases/{case_id}/analysis-results/{result_id}/selection", response_model=dict)
async def patch_analysis_selection(
    case_id: str,
    result_id: str,
    body: dict,
    current_user: AuthUserRead = Depends(require_manager),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    # Verify the result belongs to this project and org (org check already done above via project)
    analysis_result = await analysis_service.get_analysis_result_by_id(result_id, organization_id=org_id)
    if not analysis_result or analysis_result.projectId != case_id:
        raise HTTPException(status_code=404, detail="Analysis result not found.")
    changes: dict = {}
    if "polygon" in body:
        changes["selectedRepairPolygon"] = body["polygon"]
    if "manualAreaSqm" in body:
        area = body["manualAreaSqm"]
        changes["manualAreaSqm"] = float(area) if area is not None else None
        if changes["manualAreaSqm"] is not None:
            changes["finalAreaSource"] = "manual"
    updated = await analysis_service.update_manual_selection_by_result_id(
        result_id,
        changes,
        organization_id=org_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Analysis result not found.")
    return {"id": updated.id, "status": "ok"}


@router.post("/analysis-jobs/{job_id}/retry", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(get_settings().rate_limit_analysis_jobs)
async def retry_analysis_job(
    job_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(require_manager),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
    job_queue=Depends(get_job_queue),
) -> AnalysisTriggerResponse:
    org_id = resolve_org_id(current_user)
    original_job = await analysis_service.get_job(job_id, organization_id=org_id)
    if not original_job:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="analysis_job_retry", resource_id=job_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    settings = get_settings()
    new_job = await analysis_service.retry_job(
        job_id,
        organization_id=org_id,
        is_superadmin_context=current_user.isSuperAdmin,
        job_queue=job_queue,
    )
    if not new_job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    if job_queue is not None:
        try:
            await enqueue_analysis_job(
                job_queue,
                job_id=new_job.id,
                project_id=new_job.project_id,
                organization_id=org_id,
                is_superadmin_context=current_user.isSuperAdmin,
                max_depth=settings.analysis_queue_max_depth,
            )
        except AnalysisJobQueueCapacityExceededError:
            await analysis_service.cancel_analysis_job(new_job.id, organization_id=org_id)
            raise HTTPException(status_code=429, detail="Analysis queue is full. Please retry later.")
    else:
        logger.warning("job_queue.unavailable", job_id=new_job.id, action="retry_analysis_job")
    return AnalysisTriggerResponse(
        jobId=new_job.id,
        status=new_job.status,
        workTypeCode=getattr(new_job, "requested_work_type_code", None),
        analysisProfileCode=getattr(new_job, "resolved_analysis_profile_code", None),
        analysisProfileVersion=getattr(new_job, "resolved_analysis_profile_version", None),
        provider=analysis_service.provider_key,
    )
