import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_current_user, get_photo_service, get_project_service, resolve_org_id
from app.core.audit import log_cross_tenant_denied
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.metrics import UPLOAD_REJECTIONS_TOTAL
from app.schemas.auth import AuthUserRead
from app.schemas.photo import (
    AnalysisReferencePhotoResponse,
    DeletePhotoResponse,
    PhotoListResponse,
    PhotoMoveRequest,
    PhotoUploadResponse,
    PrimaryPhotoResponse,
)
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService
from app.storage.backend import UploadValidationError

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["images"])


def _upload_error_status_code(exc: UploadValidationError) -> int:
    status_code = getattr(exc, "status_code", status.HTTP_400_BAD_REQUEST)
    detail = str(exc)
    if status_code == status.HTTP_400_BAD_REQUEST and detail.startswith("File too large:"):
        return status.HTTP_413_CONTENT_TOO_LARGE
    if status_code == status.HTTP_400_BAD_REQUEST and detail.startswith(
        ("Unsupported Content-Type", "Unsupported file type", "Content-Type mismatch", "File extension mismatch")
    ):
        return status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    if status_code in {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_413_CONTENT_TOO_LARGE,
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    }:
        return status_code
    return status.HTTP_400_BAD_REQUEST


def _upload_error_reason(exc: UploadValidationError) -> str:
    detail = str(exc)
    if detail.startswith("File too large:"):
        return "file_too_large"
    if detail.startswith("Unsupported Content-Type"):
        return "unsupported_content_type"
    if detail.startswith("Unsupported file type"):
        return "unsupported_file_type"
    if detail.startswith("Content-Type mismatch"):
        return "content_type_mismatch"
    if detail.startswith("File extension mismatch"):
        return "file_extension_mismatch"
    if "filename" in detail.lower():
        return "invalid_filename"
    if "image" in detail.lower() or "corrupt" in detail.lower():
        return "invalid_image_content"
    return "invalid_upload"


@router.get("/cases/{case_id}/images", response_model=PhotoListResponse)
@limiter.limit(get_settings().rate_limit_read_list)
async def list_case_images(
    case_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    items, meta = await photo_service.list_photos(case_id)
    return PhotoListResponse(items=items, meta=meta)


@router.post("/cases/{case_id}/images", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_upload)
async def upload_case_images(
    request: Request,
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoUploadResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")

    content_type = request.headers.get("content-type", "")
    uploaded = []
    if "application/json" in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "JSON metadata-only uploads are not supported. "
                "Use multipart/form-data with real image file bytes."
            ),
        )
    elif "multipart/form-data" in content_type:
        form = await request.form()
        upload_files = [value for key, value in form.multi_items() if key == "files" and hasattr(value, "read")]
        is_primary = str(form.get("isPrimary", "false")).lower() == "true"
        if not upload_files:
            raise HTTPException(status_code=400, detail="files field is required.")
        for index, file in enumerate(upload_files):
            try:
                uploaded.append(await photo_service.create_multipart_photo(project, file, is_primary=is_primary and index == 0))
            except UploadValidationError as exc:
                reason_code = _upload_error_reason(exc)
                status_code = _upload_error_status_code(exc)
                UPLOAD_REJECTIONS_TOTAL.labels(
                    reason=reason_code,
                    status_code=str(status_code),
                ).inc()
                logger.warning(
                    "photo.upload_rejected",
                    project_id=case_id,
                    user_id=current_user.id,
                    filename=getattr(file, "filename", None),
                    reason=reason_code,
                    status_code=status_code,
                )
                raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=400,
            detail="This endpoint expects multipart/form-data with one or more files fields.",
        )

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
@limiter.limit(get_settings().rate_limit_read_detail)
async def get_image_preview(
    image_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    photo_service: PhotoService = Depends(get_photo_service),
):
    org_id = resolve_org_id(current_user)
    photo = await photo_service.get_photo_by_id_in_org(
        image_id,
        organization_id=org_id,
    )
    if not photo:
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
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
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
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
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
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
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
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    deleted = await photo_service.delete_photo(case_id, image_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Image not found.")
    return DeletePhotoResponse(message="Image removed.")
