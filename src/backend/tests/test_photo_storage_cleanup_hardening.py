from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from PIL import Image


def _make_project(project_id: str = "prj_test") -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.organization_id = "org_test"
    return project


def _make_upload_file() -> MagicMock:
    file = MagicMock(spec=UploadFile)
    file.filename = "photo.jpg"
    file.content_type = "image/jpeg"
    file.size = None
    file.read = AsyncMock(return_value=b"unused")
    return file


def _make_fake_settings(limit_mb: int = 20) -> MagicMock:
    settings = MagicMock()
    settings.max_upload_size_mb = limit_mb
    settings.worker_heavy_concurrency = 1
    settings.worker_concurrency = 2
    settings.analysis_queue_max_depth = 50
    settings.heavy_queue_max_depth = 50
    settings.backpressure_max_queued_jobs = 100
    settings.backpressure_max_concurrent_jobs = 4
    return settings


def _make_validated_upload(content: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        original_filename="photo.jpg",
        storage_filename="photo.jpg",
        actual_mime_type="image/jpeg",
        content=content,
        file_size=len(content),
        filename_was_missing=False,
        content_type_was_missing=False,
    )


def _make_jpeg(width: int = 1200, height: int = 900) -> bytes:
    image = Image.new("RGB", (width, height), (64, 96, 160))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


class TestPhotoPersistenceCleanupHardening:
    @pytest.mark.asyncio
    async def test_create_multipart_photo_cleans_original_when_db_persist_fails(self):
        from app.services.photo_service import PhotoService

        content = _make_jpeg()
        validated_upload = _make_validated_upload(content)
        project = _make_project()

        repo = AsyncMock()
        repo.count_photos = AsyncMock(return_value=0)
        repo.clear_primary = AsyncMock()
        repo.get_next_sort_order = AsyncMock(return_value=1)
        repo.add_photo = AsyncMock(side_effect=RuntimeError("db insert failed"))

        service = PhotoService(repo, work_queue=MagicMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_photo_upload", return_value=validated_upload),
            patch("app.services.photo_service.get_image_dimensions", return_value=(1200, 900)),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
            patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_delete,
        ):
            with pytest.raises(RuntimeError, match="db insert failed"):
                await service.create_multipart_photo(project, _make_upload_file(), is_primary=True)

        mock_delete.assert_awaited_once_with(relative_storage_key="projects/prj_test/photo.jpg")

    @pytest.mark.asyncio
    async def test_variant_processing_cleans_partial_files_and_clears_metadata(self):
        from app.services.photo_service import PhotoService

        content = _make_jpeg(2400, 1800)
        photo = MagicMock()
        photo.id = "pho_1"
        photo.project_id = "prj_test"
        photo.processing_status = "uploaded"
        photo.preview_storage_key = "projects/prj_test/preview/photo.jpg"
        photo.preview_file_size = 12345
        photo.preview_width = 1600
        photo.preview_height = 1200
        photo.ai_input_storage_key = "projects/prj_test/ai/photo.jpg"
        photo.ai_input_file_size = 9876
        photo.ai_input_width = 1280
        photo.ai_input_height = 960

        async def fake_write(*, relative_storage_key: str, content: bytes) -> None:
            if relative_storage_key.endswith("/ai/photo.jpg"):
                raise OSError("disk full")

        repo = AsyncMock()
        repo.update_photo = AsyncMock(side_effect=lambda persisted_photo: persisted_photo)
        service = PhotoService(repo)

        with (
            patch("app.services.photo_service.write_storage_file", side_effect=fake_write),
            patch("app.services.photo_service.delete_storage_file", new_callable=AsyncMock) as mock_delete,
        ):
            result = await service._process_multipart_photo_variants(photo, content)

        assert result.processing_status == "failed"
        assert result.preview_storage_key is None
        assert result.preview_file_size is None
        assert result.preview_width is None
        assert result.preview_height is None
        assert result.ai_input_storage_key is None
        assert result.ai_input_file_size is None
        assert result.ai_input_width is None
        assert result.ai_input_height is None
        mock_delete.assert_awaited_once_with(relative_storage_key="projects/prj_test/preview/photo.jpg")
        assert repo.update_photo.await_count == 2
