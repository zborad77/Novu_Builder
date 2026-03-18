from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_analysis_service, get_project_service
from app.schemas.analysis import AnalysisPatch, AnalysisResultRead, AnalysisTriggerResponse
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/analysis", tags=["analysis"])


@router.get("", response_model=AnalysisResultRead)
async def get_latest_analysis(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResultRead:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await analysis_service.get_latest_result(project_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No analysis result found.")
    return result


@router.post("", response_model=AnalysisTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisTriggerResponse:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        payload = await analysis_service.trigger_analysis(project)
        return AnalysisTriggerResponse(**payload)
    except ValueError as error:
        provider_info = analysis_service.describe_provider()
        raise HTTPException(
            status_code=503,
            detail={
                "error": str(error),
                "provider": provider_info.get("providerKey"),
            },
        ) from error


@router.patch("", response_model=AnalysisResultRead)
async def patch_latest_analysis(
    project_id: str,
    payload: AnalysisPatch,
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResultRead:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    changes: dict = {}
    if "referencePhotoId" in payload.model_fields_set:
        changes["referencePhotoId"] = payload.referencePhotoId
    if "selectedRepairPolygon" in payload.model_fields_set:
        changes["selectedRepairPolygon"] = (
            [point.model_dump() for point in payload.selectedRepairPolygon]
            if payload.selectedRepairPolygon is not None
            else None
        )
    if "manualAreaSqm" in payload.model_fields_set:
        changes["manualAreaSqm"] = payload.manualAreaSqm
    if "finalAreaSource" in payload.model_fields_set:
        changes["finalAreaSource"] = payload.finalAreaSource

    updated = await analysis_service.update_manual_selection(project_id, changes)
    if updated is None:
        raise HTTPException(status_code=404, detail="No analysis result found.")
    return updated
