import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_current_user, get_photo_service, get_project_service, resolve_org_id
from app.core.audit import log_cross_tenant_denied
from app.schemas.auth import AuthUserRead

logger = structlog.get_logger(__name__)
from app.schemas.photo import (
    AnalysisReferencePhotoResponse,
    DeletePhotoResponse,
    PhotoJsonUploadRequest,
    PhotoListResponse,
    PhotoMoveRequest,
    PhotoUploadResponse,
    PrimaryPhotoResponse,
    ProjectPhotoRead,
)
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService

router = APIRouter(tags=["images"])


@router.get("/cases/{case_id}/images", response_model=PhotoListResponse)
async def list_case_images(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    org_id = resolve_org_id(current_user)
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    items, meta = await photo_service.list_photos(case_id)
    return PhotoListResponse(items=items, meta=meta)


@router.post("/cases/{case_id}/images", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_case_images(
    request: Request,
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoUploadResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")

    content_type = request.headers.get("content-type", "")
    uploaded = []
    if "application/json" in content_type:
        payload = PhotoJsonUploadRequest.model_validate(await request.json())
        if not payload.files:
            raise HTTPException(status_code=400, detail="files array is required.")
        for item in payload.files:
            uploaded.append(await photo_service.create_json_photo(project, item.model_dump()))
    elif "multipart/form-data" in content_type:
        form = await request.form()
        upload_files = [value for key, value in form.multi_items() if key == "files" and hasattr(value, "read")]
        is_primary = str(form.get("isPrimary", "false")).lower() == "true"
        if not upload_files:
            raise HTTPException(status_code=400, detail="files field is required.")
        for index, file in enumerate(upload_files):
            uploaded.append(await photo_service.create_multipart_photo(project, file, is_primary=is_primary and index == 0))
    else:
        raise HTTPException(status_code=400, detail="This endpoint expects multipart/form-data files or a JSON body with a files array.")

    return PhotoUploadResponse(
        uploaded=[
            {
                "id": photo.id,
                "storageKey": photo.storageKey,
                "isPrimary": photo.isPrimary,
                "processingStatus": photo.processingStatus,
                "variants": photo.variants,
            }
            for photo in uploaded
        ]
    )


@router.get("/images/{image_id}/preview")
async def get_image_preview(
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
):
    photo = await photo_service.get_photo_by_id(image_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project(photo.projectId, organization_id=org_id)
    if not project:
        if not current_user.isSuperAdmin:
            log_cross_tenant_denied(
                logger,
                resource="image_preview", resource_id=image_id,
                user_id=current_user.id, org_id=current_user.organizationId,
            )
        raise HTTPException(status_code=404, detail="Image not found.")
    preview_url = photo.variants.preview.url or photo.url
    return RedirectResponse(url=preview_url)


@router.patch("/cases/{case_id}/images/{image_id}/primary", response_model=PrimaryPhotoResponse)
async def set_case_primary_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PrimaryPhotoResponse:
    org_id = resolve_org_id(current_user)
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    photo = await photo_service.set_primary_photo(case_id, image_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    return PrimaryPhotoResponse(message="Primary image updated.", photo=photo)


@router.patch("/cases/{case_id}/images/{image_id}/analysis-reference", response_model=AnalysisReferencePhotoResponse)
async def set_case_analysis_reference_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> AnalysisReferencePhotoResponse:
    org_id = resolve_org_id(current_user)
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    try:
        photo = await photo_service.set_analysis_reference_photo(case_id, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    return AnalysisReferencePhotoResponse(message="Analysis reference image updated.", photo=photo)


@router.patch("/cases/{case_id}/images/{image_id}/move", response_model=PhotoListResponse)
async def move_case_image(
    case_id: str,
    image_id: str,
    payload: PhotoMoveRequest,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    org_id = resolve_org_id(current_user)
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")

    moved = await photo_service.move_photo(case_id, image_id, payload.direction)
    if not moved:
        raise HTTPException(status_code=404, detail="Image not found.")

    items, meta = moved
    return PhotoListResponse(items=items, meta=meta)


@router.delete("/cases/{case_id}/images/{image_id}", response_model=DeletePhotoResponse)
async def delete_case_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> DeletePhotoResponse:
    org_id = resolve_org_id(current_user)
    detail = await project_service.get_project_detail(case_id, organization_id=org_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    deleted = await photo_service.delete_photo(case_id, image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Image not found.")
    return DeletePhotoResponse(message="Image removed.")
