import asyncio
from uuid import uuid4

import structlog
from fastapi import UploadFile

from app.models import Project, ProjectPhoto
from app.core.config import get_settings
from app.repositories.photo_repository import PhotoRepository
from app.schemas.photo import ProjectPhotoRead
from app.storage.local_photo_storage import (
    delete_storage_file,
    get_image_dimensions,
    get_public_url,
    resize_image_bytes,
    save_original_photo,
    write_storage_file,
)

logger = structlog.get_logger(__name__)

MIN_PROJECT_PHOTOS = 3


def _get_scaled_dimensions(width: int | None, height: int | None, max_edge: int) -> tuple[int | None, int | None]:
    if not width or not height or width <= 0 or height <= 0:
        return None, None
    current_max_edge = max(width, height)
    if current_max_edge <= max_edge:
        return width, height
    scale = max_edge / current_max_edge
    return max(1, round(width * scale)), max(1, round(height * scale))


def _estimate_derived_file_size(
    original_size: int,
    derived_width: int | None,
    derived_height: int | None,
    original_width: int | None,
    original_height: int | None,
    compression_ratio: float,
) -> int | None:
    if not original_size or not derived_width or not derived_height or not original_width or not original_height:
        return None
    area_ratio = (derived_width * derived_height) / (original_width * original_height)
    return max(20_000, round(original_size * area_ratio * compression_ratio))


def build_derived_variants(project_id: str, filename: str, *, original_size: int, width: int | None, height: int | None) -> dict:
    preview_width, preview_height = _get_scaled_dimensions(width, height, 1600)
    ai_width, ai_height = _get_scaled_dimensions(width, height, 1280)
    return {
        "preview_storage_key": f"projects/{project_id}/preview/{filename}",
        "preview_width": preview_width,
        "preview_height": preview_height,
        "preview_file_size": _estimate_derived_file_size(original_size, preview_width, preview_height, width, height, 0.72),
        "ai_input_storage_key": f"projects/{project_id}/ai/{filename}",
        "ai_input_width": ai_width,
        "ai_input_height": ai_height,
        "ai_input_file_size": _estimate_derived_file_size(original_size, ai_width, ai_height, width, height, 0.56),
    }


def _is_terminal_processing_status(status: str) -> bool:
    return status in {"ready", "failed"}


def to_read_model(photo: ProjectPhoto) -> ProjectPhotoRead:
    original_url = get_public_url(photo.storage_key)
    preview_url = get_public_url(photo.preview_storage_key) if photo.preview_storage_key else None
    ai_input_url = get_public_url(photo.ai_input_storage_key) if photo.ai_input_storage_key else None
    return ProjectPhotoRead(
        id=photo.id,
        projectId=photo.project_id,
        originalFilename=photo.original_filename,
        storageKey=photo.storage_key,
        mimeType=photo.mime_type,
        fileSize=photo.file_size,
        width=photo.width,
        height=photo.height,
        takenAt=photo.taken_at,
        exifLat=photo.exif_lat,
        exifLng=photo.exif_lng,
        processingStatus=photo.processing_status,
        isPrimary=photo.is_primary,
        isAnalysisReference=photo.is_analysis_reference,
        sortOrder=photo.sort_order,
        url=original_url,
        variants={
            "original": {
                "storageKey": photo.storage_key,
                "fileSize": photo.file_size,
                "width": photo.width,
                "height": photo.height,
                "url": original_url,
            },
            "preview": {
                "storageKey": photo.preview_storage_key,
                "fileSize": photo.preview_file_size,
                "width": photo.preview_width,
                "height": photo.preview_height,
                "url": preview_url,
            },
            "aiInput": {
                "storageKey": photo.ai_input_storage_key,
                "fileSize": photo.ai_input_file_size,
                "width": photo.ai_input_width,
                "height": photo.ai_input_height,
                "url": ai_input_url,
            },
        },
    )


class PhotoService:
    def __init__(self, repository: PhotoRepository):
        self.repository = repository

    async def _update_processing_status(self, photo: ProjectPhoto, status: str) -> ProjectPhoto:
        photo.processing_status = status
        return await self.repository.update_photo(photo)

    async def _process_multipart_photo_variants(self, photo: ProjectPhoto, content: bytes) -> ProjectPhoto:
        if _is_terminal_processing_status(photo.processing_status):
            return photo

        await self._update_processing_status(photo, "processing")

        try:
            # R-15: generate real resized variants instead of copying original bytes
            if photo.preview_storage_key:
                preview_content = await asyncio.to_thread(resize_image_bytes, content, 1600)
                await write_storage_file(relative_storage_key=photo.preview_storage_key, content=preview_content)
            if photo.ai_input_storage_key:
                ai_content = await asyncio.to_thread(resize_image_bytes, content, 1280)
                await write_storage_file(relative_storage_key=photo.ai_input_storage_key, content=ai_content)
        except Exception:
            return await self._update_processing_status(photo, "failed")

        return await self._update_processing_status(photo, "ready")

    async def _ensure_analysis_reference(self, project_id: str) -> None:
        photos = list(await self.repository.list_photos_by_project_id(project_id))
        if not photos or any(photo.is_analysis_reference for photo in photos):
            return

        ready_photos = [photo for photo in photos if photo.processing_status == "ready"]
        candidates = ready_photos or photos
        primary_candidate = next((photo for photo in candidates if photo.is_primary), None)
        chosen_photo = primary_candidate or candidates[0]

        await self.repository.clear_analysis_reference(project_id)
        chosen_photo.is_analysis_reference = True
        await self.repository.save_changes()

    async def list_photos(self, project_id: str) -> tuple[list[ProjectPhotoRead], dict]:
        await self._ensure_analysis_reference(project_id)
        photos = await self.repository.list_photos_by_project_id(project_id)
        items = [to_read_model(photo) for photo in photos]
        return items, {
            "minimumRecommendedCount": MIN_PROJECT_PHOTOS,
            "hasMinimumCount": len(items) >= MIN_PROJECT_PHOTOS,
            "primaryPhotoId": next((item.id for item in items if item.isPrimary), None),
            "analysisReferencePhotoId": next((item.id for item in items if item.isAnalysisReference), None),
            "derivativeStrategy": {
                "original": "archival-source",
                "preview": "ui-optimized-max-edge-1600",
                "aiInput": "analysis-optimized-max-edge-1280",
            },
        }

    async def get_photo_by_id(self, photo_id: str) -> ProjectPhotoRead | None:
        photo = await self.repository.get_photo_by_id(photo_id)
        if not photo:
            return None
        return to_read_model(photo)

    async def create_json_photo(self, project: Project, payload: dict) -> ProjectPhotoRead:
        filename = payload.get("originalFilename") or f"photo-{uuid4().hex[:8]}.jpg"  # intentional upload fallback
        photo_count = await self.repository.count_photos(project.id)
        is_primary = bool(payload.get("isPrimary")) or photo_count == 0
        if is_primary:
            await self.repository.clear_primary(project.id)
        variants = build_derived_variants(
            project.id,
            filename,
            original_size=payload.get("fileSize", 0),
            width=payload.get("width"),
            height=payload.get("height"),
        )
        # intentional upload fallback — client may omit mimeType; image/jpeg is the safe default
        mime_type = payload.get("mimeType") or "image/jpeg"
        if not payload.get("mimeType"):
            logger.warning("photo.create_json.mime_type_missing", project_id=project.id, fallback=mime_type)
        photo = ProjectPhoto(
            id=f"pho_{uuid4().hex[:8]}",
            project_id=project.id,
            storage_key=f"projects/{project.id}/{filename}",
            original_filename=filename,
            mime_type=mime_type,
            file_size=payload.get("fileSize", 0),
            width=payload.get("width"),
            height=payload.get("height"),
            preview_storage_key=variants["preview_storage_key"],
            preview_file_size=variants["preview_file_size"],
            preview_width=variants["preview_width"],
            preview_height=variants["preview_height"],
            ai_input_storage_key=variants["ai_input_storage_key"],
            ai_input_file_size=variants["ai_input_file_size"],
            ai_input_width=variants["ai_input_width"],
            ai_input_height=variants["ai_input_height"],
            processing_status="ready",
            taken_at=payload.get("takenAt"),
            exif_lat=payload.get("exifLat"),
            exif_lng=payload.get("exifLng"),
            is_primary=is_primary,
            is_analysis_reference=photo_count == 0,
            # NOTE: sortOrder=0 is falsy and also triggers the auto-assign path — accepted edge case
            sort_order=payload.get("sortOrder") or await self.repository.get_next_sort_order(project.id),
        )
        return to_read_model(await self.repository.add_photo(photo))

    async def create_multipart_photo(self, project: Project, file: UploadFile, *, is_primary: bool) -> ProjectPhotoRead:
        content = await file.read()
        max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(
                f"File too large: {len(content)} bytes exceeds the "
                f"{get_settings().max_upload_size_mb} MB upload limit."
            )
        # R-15: capture real image dimensions via Pillow before storing
        actual_width, actual_height = await asyncio.to_thread(get_image_dimensions, content)
        storage_key, _ = await save_original_photo(project_id=project.id, original_filename=file.filename, content=content)
        # intentional upload fallback — multipart filename is optional per HTTP spec
        filename = file.filename or f"upload-{uuid4().hex[:8]}.bin"
        if not file.filename:
            logger.warning("photo.create_multipart.filename_missing", project_id=project.id)
        photo_count = await self.repository.count_photos(project.id)
        should_be_primary = is_primary or photo_count == 0
        if should_be_primary:
            await self.repository.clear_primary(project.id)
        variants = build_derived_variants(
            project.id,
            filename,
            original_size=len(content),
            width=actual_width,
            height=actual_height,
        )
        # intentional upload fallback — content_type may be None from some HTTP clients
        content_type = file.content_type or "application/octet-stream"
        if not file.content_type:
            logger.warning("photo.create_multipart.content_type_missing", project_id=project.id, fallback=content_type)
        photo = ProjectPhoto(
            id=f"pho_{uuid4().hex[:8]}",
            project_id=project.id,
            storage_key=storage_key,
            original_filename=filename,
            mime_type=content_type,
            file_size=len(content),
            preview_storage_key=variants["preview_storage_key"],
            preview_file_size=variants["preview_file_size"],
            preview_width=variants["preview_width"],
            preview_height=variants["preview_height"],
            ai_input_storage_key=variants["ai_input_storage_key"],
            ai_input_file_size=variants["ai_input_file_size"],
            ai_input_width=variants["ai_input_width"],
            ai_input_height=variants["ai_input_height"],
            processing_status="uploaded",
            is_primary=should_be_primary,
            is_analysis_reference=photo_count == 0,
            sort_order=await self.repository.get_next_sort_order(project.id),
        )
        created_photo = await self.repository.add_photo(photo)
        processed_photo = await self._process_multipart_photo_variants(created_photo, content)
        return to_read_model(processed_photo)

    async def set_primary_photo(self, project_id: str, photo_id: str) -> ProjectPhotoRead | None:
        photo = await self.repository.get_photo(project_id, photo_id)
        if not photo:
            return None
        await self.repository.clear_primary(project_id)
        photo.is_primary = True
        updated = await self.repository.update_photo(photo)
        return to_read_model(updated)

    async def set_analysis_reference_photo(self, project_id: str, photo_id: str) -> ProjectPhotoRead | None:
        photo = await self.repository.get_photo(project_id, photo_id)
        if not photo:
            return None
        if photo.processing_status != "ready":
            raise ValueError("Analysis reference photo must be in ready state.")
        await self.repository.clear_analysis_reference(project_id)
        photo.is_analysis_reference = True
        updated = await self.repository.update_photo(photo)
        return to_read_model(updated)

    async def move_photo(self, project_id: str, photo_id: str, direction: str) -> tuple[list[ProjectPhotoRead], dict] | None:
        photos = list(await self.repository.list_photos_by_project_id(project_id))
        photo_index = next((index for index, photo in enumerate(photos) if photo.id == photo_id), -1)
        if photo_index < 0:
            return None

        target_index = photo_index - 1 if direction == "up" else photo_index + 1
        if target_index < 0 or target_index >= len(photos):
            return await self.list_photos(project_id)

        moved_photo = photos.pop(photo_index)
        photos.insert(target_index, moved_photo)

        for index, photo in enumerate(photos, start=1):
            photo.sort_order = index

        await self.repository.save_changes()
        return await self.list_photos(project_id)

    async def delete_photo(self, project_id: str, photo_id: str) -> bool:
        photo = await self.repository.get_photo(project_id, photo_id)
        if not photo:
            return False
        # R-14: delete physical files before removing the DB record
        for storage_key in (photo.storage_key, photo.preview_storage_key, photo.ai_input_storage_key):
            if storage_key:
                await delete_storage_file(relative_storage_key=storage_key)
        await self.repository.remove_photo(photo)
        return True
