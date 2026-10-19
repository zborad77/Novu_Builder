import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse
from typing import cast

from app.modules.identity.api.deps import get_current_user, resolve_org_id
from app.modules.media.api.deps import get_photo_service
from app.modules.cases.api.deps import CaseReader, get_case_reader
from app.modules.media.photo_purge import purge_photo_with_audit
from app.modules.audit.audit_log import log_cross_tenant_denied, mark_request_audited
from app.platform.config import get_settings
from app.platform.http.limiter import limiter
from app.platform.metrics import UPLOAD_REJECTIONS_TOTAL, metric_labels
from app.modules.identity.rbac import (
    Decision,
    can_purge_photo_in_tenant,
    can_soft_delete_photo,
    is_tenant_operator,
    may_soft_delete_photo_of,
)
from app.modules.identity.schemas.auth import AuthUserRead
from app.modules.media.schemas.photo import (
    AnalysisReferencePhotoResponse,
    DeletePhotoResponse,
    DeletedPhotoListResponse,
    DeletedPhotoRead,
    PhotoListResponse,
    PhotoListMeta,
    PhotoMoveRequest,
    PhotoUploadResponse,
    PrimaryPhotoResponse,
    ProjectPhotoRead,
    PurgePhotoRequest,
    PurgePhotoResponse,
    RestorePhotoResponse,
    UploadedPhotoPayload,
)
from app.modules.media.photo_service import PhotoService
from app.platform.storage.backend import UploadValidationError

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
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    items, meta = await photo_service.list_photos(case_id)
    return PhotoListResponse(
        items=_with_delete_permission(items, current_user),
        meta=PhotoListMeta.model_validate(meta),
    )


@router.post("/cases/{case_id}/images", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_upload)
async def upload_case_images(
    request: Request,
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoUploadResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")

    # Keep deterministic HTTP guardrails here; heavy-lane gating happens in PhotoService.
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
                uploaded.append(
                    await photo_service.create_multipart_photo(
                        project,
                        cast(UploadFile, file),
                        is_primary=is_primary and index == 0,
                        # Author comes from the verified identity only, never the form.
                        uploaded_by_user_id=current_user.id,
                    )
                )
            except UploadValidationError as exc:
                reason_code = _upload_error_reason(exc)
                status_code = _upload_error_status_code(exc)
                metric_labels(
                    UPLOAD_REJECTIONS_TOTAL,
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
            UploadedPhotoPayload(
                id=photo.id,
                storageKey=photo.storageKey,
                isPrimary=photo.isPrimary,
                processingStatus=photo.processingStatus,
                variants=photo.variants,
            )
            for photo in uploaded
        ]
    )


async def _get_image_preview_core(
    image_id: str,
    current_user: AuthUserRead,
    photo_service: PhotoService,
):
    """Pure application logic: org-scoped photo lookup and preview URL resolution.

    No Request dependency — directly testable without framework context.
    """
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


@router.get("/images/{image_id}/preview")
@limiter.limit(get_settings().rate_limit_read_detail)
async def get_image_preview(
    image_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    photo_service: PhotoService = Depends(get_photo_service),
):
    return await _get_image_preview_core(
        image_id=image_id,
        current_user=current_user,
        photo_service=photo_service,
    )


@router.patch("/cases/{case_id}/images/{image_id}/primary", response_model=PrimaryPhotoResponse)
async def set_case_primary_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
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
    project_service: CaseReader = Depends(get_case_reader),
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
    project_service: CaseReader = Depends(get_case_reader),
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
    return PhotoListResponse(
        items=_with_delete_permission(items, current_user),
        meta=PhotoListMeta.model_validate(meta),
    )


def _with_delete_permission(items: list[ProjectPhotoRead], user: AuthUserRead) -> list[ProjectPhotoRead]:
    """Annotate each photo with whether *this* user may soft-delete/restore it."""
    return [
        item.model_copy(update={"canDelete": may_soft_delete_photo_of(user, item.uploadedByUserId)})
        for item in items
    ]


def _enforce_photo_decision(decision: Decision, *, current_user: AuthUserRead, image_id: str, operation: str) -> None:
    if decision == "allow":
        return
    logger.warning(
        "SECURITY_EVENT: photo_operation_denied",
        operation=operation,
        user_id=current_user.id,
        role=current_user.role,
        image_id=image_id,
    )
    raise HTTPException(status_code=403, detail="Permission denied.")


@router.delete("/cases/{case_id}/images/{image_id}", response_model=DeletePhotoResponse)
async def delete_case_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> DeletePhotoResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    photo = await photo_service.get_active_photo(case_id, image_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    # Managers/company admins: any photo of the tenant. Technicians: own uploads only.
    _enforce_photo_decision(
        can_soft_delete_photo(current_user, photo),
        current_user=current_user,
        image_id=image_id,
        operation="image.delete",
    )
    deleted = await photo_service.delete_photo(case_id, image_id, deleted_by_user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Image not found.")
    return DeletePhotoResponse(message="Image removed.")


@router.get("/cases/{case_id}/images/deleted", response_model=DeletedPhotoListResponse)
async def list_deleted_case_images(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> DeletedPhotoListResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    # A technician's trash shows only photos they uploaded themselves.
    own_only = None if is_tenant_operator(current_user) else current_user.id
    photos = await photo_service.list_restorable_photos(case_id, uploaded_by_user_id=own_only)
    return DeletedPhotoListResponse(
        items=[
            DeletedPhotoRead(
                id=photo.id,
                originalFilename=photo.original_filename,
                deletedAt=photo.deleted_at,
                deletedByUserId=photo.deleted_by_user_id,
            )
            for photo in photos
        ]
    )


@router.post("/cases/{case_id}/images/{image_id}/restore", response_model=RestorePhotoResponse)
async def restore_case_image(
    case_id: str,
    image_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> RestorePhotoResponse:
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    photo = await photo_service.get_restorable_photo(case_id, image_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    _enforce_photo_decision(
        can_soft_delete_photo(current_user, photo),
        current_user=current_user,
        image_id=image_id,
        operation="image.restore",
    )
    restored = await photo_service.restore_photo(case_id, image_id)
    if not restored:
        raise HTTPException(status_code=404, detail="Image not found.")
    return RestorePhotoResponse(message="Image restored.")


@router.post("/cases/{case_id}/images/{image_id}/purge", response_model=PurgePhotoResponse)
async def purge_case_image(
    request: Request,
    response: Response,
    case_id: str,
    image_id: str,
    payload: PurgePhotoRequest,
    current_user: AuthUserRead = Depends(get_current_user),
    project_service: CaseReader = Depends(get_case_reader),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PurgePhotoResponse:
    """Permanently delete a photo and its derived files (company admin only).

    Irreversible. Superadmins use POST /admin/photos/{image_id}/purge instead.
    """
    _enforce_photo_decision(
        can_purge_photo_in_tenant(current_user),
        current_user=current_user,
        image_id=image_id,
        operation="image.purge",
    )
    org_id = resolve_org_id(current_user)
    project = await project_service.get_project_lean(case_id, organization_id=org_id)
    if not project:
        raise HTTPException(status_code=404, detail="Case not found.")
    if payload.confirmImageId != image_id:
        raise HTTPException(status_code=400, detail="confirmImageId must repeat the image id.")
    photo = await photo_service.get_photo_any_status(image_id, project_id=case_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Image not found.")
    result = await purge_photo_with_audit(
        photo_service,
        photo,
        actor=current_user,
        audit_action="image.purge",
        organization_id=project.organization_id,
    )
    mark_request_audited(request)
    if result.status == "purge_pending":
        response.status_code = status.HTTP_202_ACCEPTED
    return result
