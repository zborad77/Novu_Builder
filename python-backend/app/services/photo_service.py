import asyncio
from uuid import uuid4

import structlog
from fastapi import HTTPException, UploadFile

from app.core.backpressure import (
    collect_backpressure_snapshot,
    effective_backpressure_max_queued_jobs,
    ensure_heavy_intake_capacity,
)
from app.core.config import get_settings
from app.models import Project, ProjectPhoto
from app.repositories.photo_repository import PhotoRepository
from app.schemas.photo import ProjectPhotoRead
from app.storage.backend import (
    delete_storage_file,
    generate_presigned_url,
    get_image_dimensions,
    read_storage_file,
    resize_image_bytes,
    save_original_photo,
    validate_photo_upload,
    write_storage_file,
)
from app.worker.heavy_queue import HeavyJobQueueCapacityExceededError, enqueue_heavy_job

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
    original_url = generate_presigned_url(photo.storage_key)
    preview_url = (
        generate_presigned_url(photo.preview_storage_key)
        if photo.processing_status == "ready" and photo.preview_storage_key
        else None
    )
    ai_input_url = (
        generate_presigned_url(photo.ai_input_storage_key)
        if photo.processing_status == "ready" and photo.ai_input_storage_key
        else None
    )
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
    def __init__(self, repository: PhotoRepository, *, work_queue=None):
        self.repository = repository
        self.work_queue = work_queue

    async def _cleanup_storage_keys(self, *storage_keys: str | None) -> None:
        seen: set[str] = set()
        for storage_key in storage_keys:
            if not storage_key or storage_key in seen:
                continue
            seen.add(storage_key)
            try:
                await delete_storage_file(relative_storage_key=storage_key)
            except Exception as exc:
                logger.warning(
                    "photo.storage_cleanup_failed",
                    storage_key=storage_key,
                    error=str(exc),
                    exc_info=True,
                )

    async def _delete_storage_keys_fail_closed(self, *storage_keys: str | None) -> None:
        seen: set[str] = set()
        for storage_key in storage_keys:
            if not storage_key or storage_key in seen:
                continue
            seen.add(storage_key)
            await delete_storage_file(relative_storage_key=storage_key)

    @staticmethod
    def _clear_failed_variant_metadata(photo: ProjectPhoto) -> None:
        photo.preview_storage_key = None
        photo.preview_file_size = None
        photo.preview_width = None
        photo.preview_height = None
        photo.ai_input_storage_key = None
        photo.ai_input_file_size = None
        photo.ai_input_width = None
        photo.ai_input_height = None

    async def _update_processing_status(self, photo: ProjectPhoto, status: str) -> ProjectPhoto:
        photo.processing_status = status
        return await self.repository.update_photo(photo)

    async def _process_multipart_photo_variants(self, photo: ProjectPhoto, content: bytes) -> ProjectPhoto:
        if _is_terminal_processing_status(photo.processing_status):
            return photo

        await self._update_processing_status(photo, "processing")
        written_storage_keys: list[str] = []

        try:
            if photo.preview_storage_key:
                preview_content = await asyncio.to_thread(resize_image_bytes, content, 1600)
                await write_storage_file(relative_storage_key=photo.preview_storage_key, content=preview_content)
                written_storage_keys.append(photo.preview_storage_key)
            if photo.ai_input_storage_key:
                ai_content = await asyncio.to_thread(resize_image_bytes, content, 1280)
                await write_storage_file(relative_storage_key=photo.ai_input_storage_key, content=ai_content)
                written_storage_keys.append(photo.ai_input_storage_key)
        except Exception as exc:
            logger.error(
                "photo.variant_processing_failed",
                photo_id=photo.id,
                project_id=photo.project_id,
                error=str(exc),
                exc_info=True,
            )
            await self._cleanup_storage_keys(*written_storage_keys)
            self._clear_failed_variant_metadata(photo)
            return await self._update_processing_status(photo, "failed")

        return await self._update_processing_status(photo, "ready")

    async def process_photo_variants_by_id(self, photo_id: str) -> ProjectPhotoRead | None:
        photo = await self.repository.get_photo_by_id(photo_id)
        if not photo:
            return None
        if _is_terminal_processing_status(photo.processing_status):
            return to_read_model(photo)

        original_bytes = await read_storage_file(relative_storage_key=photo.storage_key)
        if original_bytes is None:
            logger.error(
                "photo.variant_processing_source_missing",
                photo_id=photo.id,
                project_id=photo.project_id,
                storage_key=photo.storage_key,
            )
            self._clear_failed_variant_metadata(photo)
            failed = await self._update_processing_status(photo, "failed")
            return to_read_model(failed)

        processed = await self._process_multipart_photo_variants(photo, original_bytes)
        return to_read_model(processed)

    async def _ensure_analysis_reference(self, project_id: str) -> None:
        photos = list(await self.repository.list_photos_by_project_id(project_id))
        if not photos or any(photo.is_analysis_reference for photo in photos):
            return

        ready_photos = [photo for photo in photos if photo.processing_status == "ready"]
        if not ready_photos:
            return
        primary_candidate = next((photo for photo in ready_photos if photo.is_primary), None)
        chosen_photo = primary_candidate or ready_photos[0]

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

    async def get_photo_by_id_in_org(
        self,
        photo_id: str,
        *,
        organization_id: str | None,
    ) -> ProjectPhotoRead | None:
        photo = await self.repository.get_photo_by_id_in_org(
            photo_id,
            organization_id=organization_id,
        )
        if not photo:
            return None
        return to_read_model(photo)

    async def create_multipart_photo(self, project: Project, file: UploadFile, *, is_primary: bool) -> ProjectPhotoRead:
        settings = get_settings()
        queue_processing_enabled = settings.worker_heavy_concurrency > 0
        if queue_processing_enabled:
            snapshot = await collect_backpressure_snapshot(
                settings=settings,
                job_queue=self.work_queue,
            )
            ensure_heavy_intake_capacity(
                snapshot,
                settings=settings,
                surface="photo_upload_api",
            )

        max_upload_size_mb = settings.max_upload_size_mb
        validated_upload = await validate_photo_upload(
            file,
            max_bytes=max_upload_size_mb * 1024 * 1024,
            max_upload_size_mb=max_upload_size_mb,
        )
        content = validated_upload.content
        actual_mime_type = validated_upload.actual_mime_type
        actual_width, actual_height = await asyncio.to_thread(get_image_dimensions, content)
        storage_key, _ = await save_original_photo(
            project_id=project.id,
            original_filename=validated_upload.storage_filename,
            content=content,
        )
        try:
            if validated_upload.filename_was_missing:
                logger.warning(
                    "photo.create_multipart.filename_missing",
                    project_id=project.id,
                    fallback=validated_upload.original_filename,
                )
            photo_count = await self.repository.count_photos(project.id)
            should_be_primary = is_primary or photo_count == 0
            if should_be_primary:
                await self.repository.clear_primary(project.id)
            variants = build_derived_variants(
                project.id,
                validated_upload.storage_filename,
                original_size=validated_upload.file_size,
                width=actual_width,
                height=actual_height,
            )
            if validated_upload.content_type_was_missing:
                logger.warning(
                    "photo.create_multipart.content_type_missing",
                    project_id=project.id,
                    fallback=actual_mime_type,
                )
            photo = ProjectPhoto(
                id=f"pho_{uuid4().hex[:8]}",
                project_id=project.id,
                status="active",
                storage_key=storage_key,
                original_filename=validated_upload.original_filename,
                mime_type=actual_mime_type,
                file_size=validated_upload.file_size,
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
        except Exception as exc:
            logger.error(
                "photo.persistence_failed_after_storage_write",
                project_id=project.id,
                storage_key=storage_key,
                error=str(exc),
                exc_info=True,
            )
            await self._cleanup_storage_keys(storage_key)
            raise
        if queue_processing_enabled:
            try:
                await enqueue_heavy_job(
                    self.work_queue,
                    job_type="photo_variant_processing",
                    project_id=project.id,
                    organization_id=project.organization_id,
                    photo_id=created_photo.id,
                    max_depth=settings.heavy_queue_max_depth,
                    max_global_queued=effective_backpressure_max_queued_jobs(settings),
                )
                return to_read_model(created_photo)
            except HeavyJobQueueCapacityExceededError as exc:
                created_photo.processing_status = "failed"
                await self.repository.update_photo(created_photo)
                logger.warning(
                    "photo.variant_queue_enqueue_rejected",
                    photo_id=created_photo.id,
                    project_id=project.id,
                    error=str(exc),
                    queued=exc.queued,
                    processing=exc.processing,
                    max_depth=exc.max_depth,
                )
                raise HTTPException(status_code=429, detail="Photo processing queue is full. Please retry later.")
            except Exception as exc:
                created_photo.processing_status = "failed"
                await self.repository.update_photo(created_photo)
                logger.warning(
                    "photo.variant_queue_enqueue_unavailable",
                    photo_id=created_photo.id,
                    project_id=project.id,
                    error=str(exc),
                    exc_info=True,
                )
                raise HTTPException(status_code=503, detail="Photo processing queue is unavailable.")

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
        photo.is_primary = False
        photo.is_analysis_reference = False
        await self.repository.update_status(photo, "pending_delete")
        return True

    async def cleanup_pending_deletes(self, *, limit: int = 100) -> int:
        pending_photos = await self.repository.list_pending_delete(limit=limit)
        if not pending_photos:
            return 0

        deleted_count = 0
        for photo in pending_photos:
            try:
                await self._delete_storage_keys_fail_closed(
                    photo.storage_key,
                    photo.preview_storage_key,
                    photo.ai_input_storage_key,
                )
            except Exception as exc:
                logger.warning(
                    "photo.pending_delete_cleanup_failed",
                    photo_id=photo.id,
                    project_id=photo.project_id,
                    error=str(exc),
                    exc_info=True,
                )
                continue

            await self.repository.update_status(photo, "deleted")
            deleted_count += 1

        return deleted_count
