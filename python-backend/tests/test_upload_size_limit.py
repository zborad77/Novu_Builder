from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image


def _make_upload_file(content: bytes, filename: str = "photo.jpg", *, content_type: str | None = "image/jpeg") -> MagicMock:
    file = MagicMock(spec=UploadFile)
    file.filename = filename
    file.content_type = content_type
    file.read = AsyncMock(return_value=content)
    return file


def _make_project(project_id: str = "prj_test") -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.organization_id = "org_test"
    return project


def _make_fake_settings(limit_mb: int) -> MagicMock:
    settings = MagicMock()
    settings.max_upload_size_mb = limit_mb
    return settings


def _make_image_bytes(fmt: str) -> bytes:
    image = Image.new("RGB", (2, 2), (0, 128, 0))
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _make_validated_upload(content: bytes, *, filename: str = "photo.jpg", mime_type: str = "image/jpeg") -> SimpleNamespace:
    return SimpleNamespace(
        original_filename=filename,
        storage_filename=filename,
        actual_mime_type=mime_type,
        content=content,
        file_size=len(content),
        filename_was_missing=False,
        content_type_was_missing=False,
    )


class TestPhotoServiceSizeFlow:
    @pytest.mark.asyncio
    async def test_file_within_limit_proceeds(self):
        from app.services.photo_service import PhotoService

        content = b"x" * (5 * 1024 * 1024)
        validated_upload = _make_validated_upload(content)
        project = _make_project()

        created_photo = MagicMock(
            id="pho_1",
            project_id=project.id,
            original_filename="photo.jpg",
            storage_key="projects/prj_test/photo.jpg",
            mime_type="image/jpeg",
            file_size=len(content),
            width=None,
            height=None,
            preview_storage_key=None,
            preview_file_size=None,
            preview_width=None,
            preview_height=None,
            ai_input_storage_key=None,
            ai_input_file_size=None,
            ai_input_width=None,
            ai_input_height=None,
            processing_status="uploaded",
            taken_at=None,
            exif_lat=None,
            exif_lng=None,
            is_primary=True,
            is_analysis_reference=True,
            sort_order=1,
        )
        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings(20)),
            patch("app.services.photo_service.validate_photo_upload", return_value=validated_upload),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
        ):
            result = await service.create_multipart_photo(project, _make_upload_file(content), is_primary=True)

        assert result is not None

    @pytest.mark.asyncio
    async def test_file_exactly_at_limit_proceeds(self):
        from app.services.photo_service import PhotoService

        limit_mb = 10
        content = b"x" * (limit_mb * 1024 * 1024)
        validated_upload = _make_validated_upload(content)
        project = _make_project()

        created_photo = MagicMock(
            id="pho_2",
            project_id=project.id,
            original_filename="photo.jpg",
            storage_key="projects/prj_test/photo.jpg",
            mime_type="image/jpeg",
            file_size=len(content),
            width=None,
            height=None,
            preview_storage_key=None,
            preview_file_size=None,
            preview_width=None,
            preview_height=None,
            ai_input_storage_key=None,
            ai_input_file_size=None,
            ai_input_width=None,
            ai_input_height=None,
            processing_status="uploaded",
            taken_at=None,
            exif_lat=None,
            exif_lng=None,
            is_primary=False,
            is_analysis_reference=False,
            sort_order=2,
        )
        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=1)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=2)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings(limit_mb)),
            patch("app.services.photo_service.validate_photo_upload", return_value=validated_upload),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
        ):
            result = await service.create_multipart_photo(project, _make_upload_file(content), is_primary=False)

        assert result is not None


class TestValidatePhotoUploadSizeGuard:
    @pytest.mark.asyncio
    async def test_file_over_limit_raises_value_error(self):
        from app.storage.local_photo_storage import validate_photo_upload

        limit_mb = 10
        content = b"x" * (limit_mb * 1024 * 1024 + 1)
        mock_file = _make_upload_file(content)

        with pytest.raises(ValueError, match="File too large"):
            await validate_photo_upload(
                mock_file,
                max_bytes=limit_mb * 1024 * 1024,
                max_upload_size_mb=limit_mb,
            )

    @pytest.mark.asyncio
    async def test_rejects_before_read_when_declared_size_exceeds_limit(self):
        from app.storage.local_photo_storage import validate_photo_upload

        limit_mb = 10
        mock_file = MagicMock(spec=UploadFile)
        mock_file.size = limit_mb * 1024 * 1024 + 1
        mock_file.filename = "photo.jpg"
        mock_file.content_type = "image/jpeg"
        mock_file.read = AsyncMock(return_value=b"x")

        with pytest.raises(ValueError, match="Content-Length"):
            await validate_photo_upload(
                mock_file,
                max_bytes=limit_mb * 1024 * 1024,
                max_upload_size_mb=limit_mb,
            )

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_bounded_read_uses_limit_plus_one(self):
        from app.storage.local_photo_storage import validate_photo_upload

        limit_mb = 10
        content = b"x" * (limit_mb * 1024 * 1024 + 1)
        mock_file = _make_upload_file(content)
        mock_file.size = None

        with pytest.raises(ValueError, match="File too large"):
            await validate_photo_upload(
                mock_file,
                max_bytes=limit_mb * 1024 * 1024,
                max_upload_size_mb=limit_mb,
            )

        mock_file.read.assert_awaited_once_with(limit_mb * 1024 * 1024 + 1)

    @pytest.mark.asyncio
    async def test_guard_skipped_when_size_is_none(self):
        from app.storage.local_photo_storage import validate_photo_upload

        limit_mb = 10
        oversized = b"x" * (limit_mb * 1024 * 1024 + 1)
        mock_file = _make_upload_file(oversized)
        mock_file.size = None

        with pytest.raises(ValueError, match="File too large"):
            await validate_photo_upload(
                mock_file,
                max_bytes=limit_mb * 1024 * 1024,
                max_upload_size_mb=limit_mb,
            )

    @pytest.mark.asyncio
    async def test_guard_skipped_when_size_not_integer(self):
        from app.storage.local_photo_storage import validate_photo_upload

        jpeg_bytes = _make_image_bytes("JPEG")
        mock_file = _make_upload_file(jpeg_bytes)

        validated_upload = await validate_photo_upload(
            mock_file,
            max_bytes=10 * 1024 * 1024,
            max_upload_size_mb=10,
        )

        assert validated_upload.actual_mime_type == "image/jpeg"


class TestUploadRouteSizeLimit:
    @pytest.mark.asyncio
    async def test_route_returns_413_on_oversize(self):
        from app.api.routes.images import upload_case_images
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService
        from app.storage.backend import UploadValidationError

        project = _make_project()
        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}
        mock_form = MagicMock()
        mock_form.multi_items = MagicMock(return_value=[("files", _make_upload_file(b"x" * 1024))])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(
            side_effect=UploadValidationError("File too large: more than 20971520 bytes exceeds the 20 MB upload limit.")
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_test",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 413
        assert "File too large" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_route_returns_201_within_limit(self):
        from app.api.routes.images import upload_case_images
        from app.schemas.photo import ProjectPhotoRead
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService

        project = _make_project()
        variant = {"storageKey": None, "fileSize": None, "width": None, "height": None, "url": None}
        photo_read = MagicMock(spec=ProjectPhotoRead)
        photo_read.id = "pho_ok"
        photo_read.storageKey = "projects/prj_test/photo.jpg"
        photo_read.isPrimary = True
        photo_read.processingStatus = "uploaded"
        photo_read.variants = {"original": variant, "preview": variant, "aiInput": variant}

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}
        mock_form = MagicMock()
        mock_form.multi_items = MagicMock(return_value=[("files", _make_upload_file(b"x" * 1024))])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(return_value=photo_read)

        result = await upload_case_images(
            request=mock_request,
            case_id="prj_test",
            current_user=mock_user,
            project_service=mock_project_service,
            photo_service=mock_photo_service,
        )

        assert result is not None
        mock_photo_service.create_multipart_photo.assert_called_once()


class TestMagicBytesValidation:
    def test_non_image_bytes_rejected(self):
        from app.storage.local_photo_storage import validate_image_format

        with pytest.raises(ValueError, match="Unsupported file type"):
            validate_image_format(b"this is not an image")

    def test_random_binary_rejected(self):
        from app.storage.local_photo_storage import validate_image_format

        with pytest.raises(ValueError, match="Unsupported file type"):
            validate_image_format(bytes(range(256)) * 4)

    def test_gif_rejected(self):
        from app.storage.local_photo_storage import validate_image_format

        with pytest.raises(ValueError, match="GIF"):
            validate_image_format(_make_image_bytes("GIF"))

    def test_truncated_jpeg_rejected(self):
        from app.storage.local_photo_storage import validate_image_format

        with pytest.raises(ValueError, match="truncated or corrupted"):
            validate_image_format(_make_image_bytes("JPEG")[:16])

    def test_jpeg_accepted(self):
        from app.storage.local_photo_storage import validate_image_format

        assert validate_image_format(_make_image_bytes("JPEG")) == "image/jpeg"

    def test_png_accepted(self):
        from app.storage.local_photo_storage import validate_image_format

        assert validate_image_format(_make_image_bytes("PNG")) == "image/png"

    def test_webp_accepted(self):
        from app.storage.local_photo_storage import validate_image_format

        assert validate_image_format(_make_image_bytes("WEBP")) == "image/webp"


class TestUploadConfigValidation:
    def test_max_upload_size_must_be_positive(self):
        from app.core.config import Settings

        with pytest.raises(ValueError, match="MAX_UPLOAD_SIZE_MB"):
            Settings(MAX_UPLOAD_SIZE_MB=0)
