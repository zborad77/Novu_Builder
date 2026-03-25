import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_analysis_service, get_current_user, get_project_service, require_manager
from app.schemas.analysis import AnalysisTriggerResponse
from app.schemas.auth import AuthUserRead
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["analysis-jobs"])


@router.post("/cases/{case_id}/analysis-jobs", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    case_id: str,
    background_tasks: BackgroundTasks,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisTriggerResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    job = await analysis_service.create_job(project, user_id=current_user.id)
    background_tasks.add_task(
        analysis_service.execute_job, job.id, case_id, org_id,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    return AnalysisTriggerResponse(
        jobId=job.id,
        status=job.status,
        provider=analysis_service.provider_key,
    )


@router.get("/cases/{case_id}/analysis-jobs", response_model=list[dict])
async def list_case_analysis_jobs(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> list[dict]:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
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
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    job = await analysis_service.get_job(job_id, organization_id=org_id)
    if not job:
        if not current_user.isSuperAdmin:
            logger.warning(
                "SECURITY_EVENT: cross_tenant_access_denied",
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
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    updated = await analysis_service.cancel_analysis_job(job_id, organization_id=org_id)
    if not updated:
        if not current_user.isSuperAdmin:
            logger.warning(
                "SECURITY_EVENT: cross_tenant_access_denied",
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
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
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
    updated = await analysis_service.update_manual_selection_by_result_id(result_id, changes)
    if not updated:
        raise HTTPException(status_code=404, detail="Analysis result not found.")
    return {"id": updated.id, "status": "ok"}


@router.post("/analysis-jobs/{job_id}/retry", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_analysis_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: AuthUserRead = Depends(require_manager),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> AnalysisTriggerResponse:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    original_job = await analysis_service.get_job(job_id, organization_id=org_id)
    if not original_job:
        if not current_user.isSuperAdmin:
            logger.warning(
                "SECURITY_EVENT: cross_tenant_access_denied",
                resource="analysis_job_retry", resource_id=job_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    new_job = await analysis_service.retry_job(
        job_id,
        organization_id=org_id,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    if not new_job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    background_tasks.add_task(
        analysis_service.execute_job, new_job.id, new_job.project_id, org_id,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    return AnalysisTriggerResponse(
        jobId=new_job.id,
        status=new_job.status,
        provider=analysis_service.provider_key,
    )
