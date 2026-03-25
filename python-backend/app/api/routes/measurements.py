from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_analysis_service, get_current_user, get_project_service
from app.schemas.auth import AuthUserRead
from app.schemas.measurement import MeasurementRead, MeasurementUpsert
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService

router = APIRouter(tags=["measurements"])


def _normalize_polygon(points) -> list[dict[str, float]] | None:
    if not points:
        return None

    normalized: list[dict[str, float]] = []
    for point in points:
        if isinstance(point, dict):
            normalized.append({"x": point.get("x"), "y": point.get("y")})
            continue

        normalized.append({"x": getattr(point, "x", None), "y": getattr(point, "y", None)})

    return normalized


def _to_measurement(result) -> MeasurementRead:
    return MeasurementRead(
        id=result.id,
        caseId=result.projectId,
        referenceImageId=result.referencePhotoId,
        selectedRepairPolygon=_normalize_polygon(result.selectedRepairPolygon),
        aiAreaSqm=result.estimatedAreaSqm,
        manualAreaSqm=result.manualAreaSqm,
        finalAreaSource=result.finalAreaSource,
        confirmed=result.finalAreaSource == "manual" and result.manualAreaSqm is not None,
        createdAt=result.createdAt,
        updatedAt=result.createdAt,
    )


@router.post("/cases/{case_id}/measurements", response_model=MeasurementRead, status_code=status.HTTP_201_CREATED)
async def create_or_update_measurement(
    case_id: str,
    payload: MeasurementUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> MeasurementRead:
    org_id = None if current_user.isSuperAdmin else current_user.organizationId
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    changes = payload.model_dump(exclude_unset=True)
    if "referenceImageId" in changes:
        changes["referencePhotoId"] = changes.pop("referenceImageId")
    updated = await analysis_service.update_manual_selection(case_id, changes)
    if not updated:
        raise HTTPException(status_code=404, detail="No analysis result found.")
    return _to_measurement(updated)


@router.patch("/measurements/{measurement_id}", response_model=MeasurementRead)
async def patch_measurement(
    measurement_id: str,
    payload: MeasurementUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> MeasurementRead:
    existing = await analysis_service.get_analysis_result_by_id(measurement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    if not current_user.isSuperAdmin:
        project = await project_service.get_project(existing.projectId, organization_id=current_user.organizationId)
        if not project:
            raise HTTPException(status_code=404, detail="Measurement not found.")
    changes = payload.model_dump(exclude_unset=True)
    if "referenceImageId" in changes:
        changes["referencePhotoId"] = changes.pop("referenceImageId")
    updated = await analysis_service.update_manual_selection_by_result_id(measurement_id, changes)
    if not updated:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    return _to_measurement(updated)


@router.post("/measurements/{measurement_id}/confirm", response_model=MeasurementRead)
async def confirm_measurement(
    measurement_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> MeasurementRead:
    existing = await analysis_service.get_analysis_result_by_id(measurement_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    if not current_user.isSuperAdmin:
        project = await project_service.get_project(existing.projectId, organization_id=current_user.organizationId)
        if not project:
            raise HTTPException(status_code=404, detail="Measurement not found.")
    updated = await analysis_service.update_manual_selection_by_result_id(
        measurement_id,
        {"finalAreaSource": "manual"},
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    return _to_measurement(updated)
