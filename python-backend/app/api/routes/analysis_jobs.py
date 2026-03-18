from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_analysis_service, get_project_service
from app.schemas.analysis import AnalysisTriggerResponse
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService

router = APIRouter(tags=["analysis-jobs"])


@router.post("/cases/{case_id}/analysis-jobs", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    case_id: str,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisTriggerResponse:
    project = await project_service.get_project(case_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    payload = await analysis_service.trigger_analysis(project)
    return AnalysisTriggerResponse(**payload)


@router.get("/cases/{case_id}/analysis-jobs", response_model=list[dict])
async def list_case_analysis_jobs(
    case_id: str,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> list[dict]:
    project = await project_service.get_project(case_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    return await analysis_service.list_jobs(case_id)


@router.get("/analysis-jobs/{job_id}", response_model=dict)
async def get_analysis_job(
    job_id: str,
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    job = await analysis_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job


@router.post("/analysis-jobs/{job_id}/cancel", response_model=dict)
async def cancel_analysis_job(
    job_id: str,
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    job = await analysis_service.cancel_analysis_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return job


@router.post("/analysis-jobs/{job_id}/retry", response_model=AnalysisTriggerResponse)
async def retry_analysis_job(
    job_id: str,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisTriggerResponse:
    job = await analysis_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    project = await project_service.get_project(job["projectId"])
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    payload = await analysis_service.retry_analysis_job(job_id, project)
    if not payload:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return AnalysisTriggerResponse(**payload)
