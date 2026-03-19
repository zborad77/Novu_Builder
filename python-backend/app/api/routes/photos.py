from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from app.api.deps import get_photo_service, get_project_service
from app.schemas.photo import (
    AnalysisReferencePhotoResponse,
    DeletePhotoResponse,
    PhotoJsonUploadRequest,
    PhotoListResponse,
    PhotoMoveRequest,
    PhotoUploadResponse,
    PrimaryPhotoResponse,
)
from app.services.photo_service import PhotoService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/photos", tags=["photos"])


@router.get("", response_model=PhotoListResponse)
async def list_photos(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    detail = await project_service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")
    items, meta = await photo_service.list_photos(project_id)
    return PhotoListResponse(items=items, meta=meta)


@router.post("", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photos(
    request: Request,
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoUploadResponse:
    project = await project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

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
        upload_files = [value for key, value in form.multi_items() if key == "files" and isinstance(value, UploadFile)]
        is_primary = str(form.get("isPrimary", "false")).lower() == "true"
        if not upload_files:
            raise HTTPException(status_code=400, detail="files field is required.")
        for index, file in enumerate(upload_files):
            uploaded.append(await photo_service.create_multipart_photo(project, file, is_primary=is_primary and index == 0))
    else:
        raise HTTPException(
            status_code=400,
            detail="This endpoint expects multipart/form-data files or a JSON body with a files array.",
        )

    return PhotoUploadResponse(uploaded=uploaded)


@router.patch("/{photo_id}/primary", response_model=PrimaryPhotoResponse)
async def set_primary_photo(
    project_id: str,
    photo_id: str,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PrimaryPhotoResponse:
    detail = await project_service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")

    photo = await photo_service.set_primary_photo(project_id, photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    return PrimaryPhotoResponse(message="Primary photo updated.", photo=photo)


@router.patch("/{photo_id}/analysis-reference", response_model=AnalysisReferencePhotoResponse)
async def set_analysis_reference_photo(
    project_id: str,
    photo_id: str,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> AnalysisReferencePhotoResponse:
    detail = await project_service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        photo = await photo_service.set_analysis_reference_photo(project_id, photo_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found.")

    return AnalysisReferencePhotoResponse(message="Analysis reference photo updated.", photo=photo)


@router.patch("/{photo_id}/move", response_model=PhotoListResponse)
async def move_photo(
    project_id: str,
    photo_id: str,
    payload: PhotoMoveRequest,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    detail = await project_service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")

    moved = await photo_service.move_photo(project_id, photo_id, payload.direction)
    if not moved:
        raise HTTPException(status_code=404, detail="Photo not found.")

    items, meta = moved
    return PhotoListResponse(items=items, meta=meta)


@router.delete("/{photo_id}", response_model=DeletePhotoResponse)
async def delete_photo(
    project_id: str,
    photo_id: str,
    project_service: ProjectService = Depends(get_project_service),
    photo_service: PhotoService = Depends(get_photo_service),
) -> DeletePhotoResponse:
    detail = await project_service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")

    removed = await photo_service.delete_photo(project_id, photo_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Photo not found.")

    return DeletePhotoResponse(message="Photo removed.")
