import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_analysis_service, get_current_user, get_project_service, resolve_org_id
from app.core.audit import log_cross_tenant_denied
from app.core.config import get_settings
from app.core.limiter import limiter
from app.schemas.auth import AuthUserRead
from app.schemas.measurement import MeasurementPolygonPoint, MeasurementRead, MeasurementUpsert
from app.services.analysis_service import AnalysisService
from app.services.project_service import ProjectService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["measurements"])


def _normalize_polygon(points) -> list[MeasurementPolygonPoint] | None:
    if not points:
        return None

    normalized: list[MeasurementPolygonPoint] = []
    for point in points:
        if isinstance(point, dict):
            x = point.get("x")
            y = point.get("y")
        else:
            x = getattr(point, "x", None)
            y = getattr(point, "y", None)
        if x is None or y is None:
            continue
        normalized.append(MeasurementPolygonPoint(x=float(x), y=float(y)))

    return normalized or None


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
@limiter.limit(get_settings().rate_limit_marker_write)
async def create_or_update_measurement(
    request: Request,
    case_id: str,
    payload: MeasurementUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> MeasurementRead:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
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
@limiter.limit(get_settings().rate_limit_marker_write)
async def patch_measurement(
    request: Request,
    measurement_id: str,
    payload: MeasurementUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> MeasurementRead:
    org_id = resolve_org_id(current_user)
    existing = await analysis_service.get_analysis_result_by_id(measurement_id, organization_id=org_id)
    if not existing:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="measurement_patch", resource_id=measurement_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Measurement not found.")
    changes = payload.model_dump(exclude_unset=True)
    if "referenceImageId" in changes:
        changes["referencePhotoId"] = changes.pop("referenceImageId")
    updated = await analysis_service.update_manual_selection_by_result_id(
        measurement_id,
        changes,
        organization_id=org_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    return _to_measurement(updated)


@router.post("/measurements/{measurement_id}/confirm", response_model=MeasurementRead)
@limiter.limit(get_settings().rate_limit_marker_write)
async def confirm_measurement(
    request: Request,
    measurement_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    project_service: ProjectService = Depends(get_project_service),
) -> MeasurementRead:
    org_id = resolve_org_id(current_user)
    existing = await analysis_service.get_analysis_result_by_id(measurement_id, organization_id=org_id)
    if not existing:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="measurement_confirm", resource_id=measurement_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Measurement not found.")
    updated = await analysis_service.update_manual_selection_by_result_id(
        measurement_id,
        {"finalAreaSource": "manual"},
        organization_id=org_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Measurement not found.")
    return _to_measurement(updated)
