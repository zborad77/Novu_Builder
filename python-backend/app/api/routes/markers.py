import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_photo_service,
    get_project_service,
    resolve_org_id,
)
from app.db.session import get_db_session
from app.core.audit import log_cross_tenant_denied
from app.core.config import get_settings
from app.core.limiter import limiter
from app.repositories.marker_repository import MarkerRepository
from app.schemas.auth import AuthUserRead
from app.schemas.marker import MarkerCreate, MarkerDeleteResponse, MarkerListResponse, MarkerRead
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/markers", tags=["markers"])


def _get_marker_repository(session: AsyncSession = Depends(get_db_session)) -> MarkerRepository:
    return MarkerRepository(session)


def _to_marker_read(m) -> MarkerRead:
    return MarkerRead(
        id=m.id,
        caseId=m.case_id,
        imageId=m.image_id,
        markerType=m.marker_type,
        markerSource=m.marker_source,
        x=m.x,
        y=m.y,
        width=m.width,
        height=m.height,
        label=m.label,
        severity=m.severity,
        createdBy=m.created_by,
        createdAt=m.created_at,
    )


@router.post("", response_model=MarkerRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_marker_write)
async def create_marker(
    request: Request,
    payload: MarkerCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
    repo: MarkerRepository = Depends(_get_marker_repository),
) -> MarkerRead:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(payload.caseId, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    # P2-B: validate imageId belongs to this case so no cross-tenant reference is stored
    if payload.imageId is not None:
        photo = await photo_service.get_photo_by_id_in_org(payload.imageId, organization_id=org_id)
        if not photo or photo.projectId != payload.caseId:
            raise HTTPException(status_code=422, detail="imageId does not belong to this case.")
    marker = await repo.create(
        case_id=payload.caseId,
        image_id=payload.imageId,
        marker_type=payload.markerType,
        marker_source="user",  # client-facing POST always produces user markers; AI pipeline writes directly via repo
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
        label=payload.label,
        severity=payload.severity,
        created_by=current_user.id,
    )
    return _to_marker_read(marker)


@router.get("", response_model=MarkerListResponse)
@limiter.limit(get_settings().rate_limit_read_list)
async def list_markers(
    request: Request,
    case_id: str | None = Query(default=None),
    image_id: str | None = Query(default=None),
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
    repo: MarkerRepository = Depends(_get_marker_repository),
) -> MarkerListResponse:
    if not case_id and not image_id:
        raise HTTPException(status_code=400, detail="Provide case_id or image_id query parameter.")
    if case_id and image_id:
        raise HTTPException(status_code=400, detail="Provide either case_id or image_id, not both.")

    org_id = resolve_org_id(current_user)

    if case_id:
        project = await project_service.get_project_lean(case_id, organization_id=org_id)
        if not project:
            raise HTTPException(status_code=404, detail="Case not found.")
        items = await repo.list_by_case(case_id)
    else:
        resolved_image_id = image_id
        if resolved_image_id is None:
            raise HTTPException(status_code=400, detail="Provide case_id or image_id query parameter.")
        # image_id path: verify the photo's project belongs to this org
        photo = await photo_service.get_photo_by_id_in_org(resolved_image_id, organization_id=org_id)
        if not photo:
            if not current_user.isSuperAdmin:
                log_cross_tenant_denied(
                    logger,
                    resource="markers_by_image", resource_id=resolved_image_id,
                    user_id=current_user.id, org_id=current_user.organizationId,
                )
            raise HTTPException(status_code=404, detail="Image not found.")
        items = await repo.list_by_image(resolved_image_id)

    return MarkerListResponse(items=[_to_marker_read(m) for m in items])


@router.delete("/{marker_id}", response_model=MarkerDeleteResponse)
@limiter.limit(get_settings().rate_limit_marker_write)
async def delete_marker(
    request: Request,
    marker_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    repo: MarkerRepository = Depends(_get_marker_repository),
) -> MarkerDeleteResponse:
    org_id = resolve_org_id(current_user)
    marker = await repo.get_by_id(marker_id)
    if not marker:
        raise HTTPException(status_code=404, detail="Marker not found.")

    # P2-A: tenant check BEFORE immutability check to prevent differential-response IDOR
    project = await project_service.get_project_lean(marker.case_id, organization_id=org_id)
    if not project:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="marker_delete", resource_id=marker_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Marker not found.")

    if marker.marker_source == "ai":
        raise HTTPException(status_code=409, detail="AI markers are immutable and cannot be deleted.")

    await repo.delete_by_id(marker_id)
    return MarkerDeleteResponse(message="Marker deleted.")
