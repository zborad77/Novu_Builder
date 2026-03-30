from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image


def _make_upload_file(
    filename: str,
    content: bytes = b"x" * 100,
    *,
    content_type: str | None = "image/jpeg",
    size: int | None = None,
) -> MagicMock:
    file = MagicMock(spec=UploadFile)
    file.filename = filename
    file.content_type = content_type
    file.size = size
    file.read = AsyncMock(return_value=content)
    return file


def _make_project(project_id: str = "prj_test") -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.organization_id = "org_test"
    return project


def _make_fake_settings(limit_mb: int = 20) -> MagicMock:
    settings = MagicMock()
    settings.max_upload_size_mb = limit_mb
    return settings


def _make_image_bytes(fmt: str) -> bytes:
    image = Image.new("RGB", (2, 2), (0, 128, 0))
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _make_created_photo(project_id: str, *, mime_type: str, filename: str, file_size: int) -> MagicMock:
    return MagicMock(
        id="pho_1",
        project_id=project_id,
        original_filename=filename,
        storage_key=f"projects/{project_id}/{filename}",
        mime_type=mime_type,
        file_size=file_size,
        width=2,
        height=2,
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


class TestPathAndFilenameGuards:
    @pytest.mark.asyncio
    async def test_double_dot_in_filename_raises_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("../../etc/passwd")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path traversal"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_path_separator_in_filename_raises_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("nested/photo.jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path separators"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_backslash_in_filename_raises_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file(r"nested\\photo.jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path separators"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_character_in_filename_raises_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo\x00.jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="control characters"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsupported_extension_rejected_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("malware.exe")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="extension"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_dot_only_basename_is_rejected_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file(".jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="non-empty base name"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_reserved_windows_filename_is_rejected_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("CON.jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="reserved device names"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_overlong_filename_is_rejected_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file(f"{'a' * 252}.jpg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="longer than 255 characters"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()


class TestMimeSpoofingAndMagicBytes:
    @pytest.mark.asyncio
    async def test_unsupported_declared_content_type_rejected_before_read(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.jpg", content_type="text/plain")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="Unsupported Content-Type"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_spoofed_content_type_is_rejected(self):
        from app.services.photo_service import PhotoService

        jpeg_bytes = _make_image_bytes("JPEG")
        mock_file = _make_upload_file("photo.jpg", jpeg_bytes, content_type="image/png")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="Content-Type mismatch"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_extension_mismatch_is_rejected(self):
        from app.services.photo_service import PhotoService

        jpeg_bytes = _make_image_bytes("JPEG")
        mock_file = _make_upload_file("photo.png", jpeg_bytes, content_type="image/jpeg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="File extension mismatch"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_corrupted_payload_is_rejected(self):
        from app.services.photo_service import PhotoService

        corrupted_jpeg = _make_image_bytes("JPEG")[:16]
        mock_file = _make_upload_file("photo.jpg", corrupted_jpeg, content_type="image/jpeg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="truncated or corrupted"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_empty_payload_is_rejected(self):
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.jpg", b"", content_type="image/jpeg")
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="payload is empty"):
                await service.create_multipart_photo(_make_project(), mock_file, is_primary=False)

    def test_unsafe_decoder_payload_is_rejected(self):
        from app.storage.local_photo_storage import validate_image_format

        with patch("PIL.Image.open", side_effect=Image.DecompressionBombError("unsafe image")):
            with pytest.raises(ValueError, match="unsafe or exceeds decoder limits"):
                validate_image_format(b"fake-image")


class TestValidUploadFlow:
    @pytest.mark.asyncio
    async def test_valid_jpeg_upload_is_preserved(self):
        from app.services.photo_service import PhotoService

        jpeg_bytes = _make_image_bytes("JPEG")
        project = _make_project()
        created_photo = _make_created_photo(project.id, mime_type="image/jpeg", filename="photo.jpg", file_size=len(jpeg_bytes))

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)
        mock_file = _make_upload_file("photo.jpg", jpeg_bytes, content_type="image/jpeg")

        with patch(
            "app.services.photo_service.save_original_photo",
            return_value=("projects/prj_test/photo.jpg", None),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result.mimeType == "image/jpeg"
        assert result.originalFilename == "photo.jpg"

    @pytest.mark.asyncio
    async def test_valid_png_upload_is_preserved(self):
        from app.services.photo_service import PhotoService

        png_bytes = _make_image_bytes("PNG")
        project = _make_project()
        created_photo = _make_created_photo(project.id, mime_type="image/png", filename="photo.png", file_size=len(png_bytes))

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)
        mock_file = _make_upload_file("photo.png", png_bytes, content_type="image/png")

        with patch(
            "app.services.photo_service.save_original_photo",
            return_value=("projects/prj_test/photo.png", None),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result.mimeType == "image/png"
        assert result.originalFilename == "photo.png"

    @pytest.mark.asyncio
    async def test_missing_content_type_uses_detected_mime_type(self):
        from app.services.photo_service import PhotoService

        jpeg_bytes = _make_image_bytes("JPEG")
        project = _make_project()
        created_photo = _make_created_photo(project.id, mime_type="image/jpeg", filename="photo.jpg", file_size=len(jpeg_bytes))

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)
        mock_file = _make_upload_file("photo.jpg", jpeg_bytes, content_type=None)

        with patch(
            "app.services.photo_service.save_original_photo",
            return_value=("projects/prj_test/photo.jpg", None),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result.mimeType == "image/jpeg"

    @pytest.mark.asyncio
    async def test_missing_filename_uses_safe_generated_name(self):
        from app.services.photo_service import PhotoService

        jpeg_bytes = _make_image_bytes("JPEG")
        project = _make_project()
        created_photo = _make_created_photo(project.id, mime_type="image/jpeg", filename="upload-safe.jpg", file_size=len(jpeg_bytes))

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=created_photo)
        mock_repo.update_photo = AsyncMock(side_effect=lambda photo: photo)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)
        mock_file = _make_upload_file("", jpeg_bytes, content_type="image/jpeg")
        validated_upload = SimpleNamespace(
            original_filename="upload-safe.jpg",
            storage_filename="upload-safe.jpg",
            actual_mime_type="image/jpeg",
            content=jpeg_bytes,
            file_size=len(jpeg_bytes),
            filename_was_missing=True,
            content_type_was_missing=False,
        )

        with (
            patch("app.services.photo_service.validate_photo_upload", return_value=validated_upload),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/upload-safe.jpg", None)),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result.originalFilename == "upload-safe.jpg"


class TestRouteMapping:
    @pytest.mark.asyncio
    async def test_route_returns_400_on_filename_validation_error(self):
        from app.api.routes.images import upload_case_images
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService
        from app.storage.backend import UploadValidationError

        project = _make_project()
        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}
        mock_file = _make_upload_file("../../etc/passwd")
        mock_form = MagicMock()
        mock_form.multi_items = MagicMock(return_value=[("files", mock_file)])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(
            side_effect=UploadValidationError("Invalid filename: path traversal sequences are not allowed.")
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_test",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 400
        assert "path traversal" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_route_returns_415_on_content_type_spoofing(self):
        from app.api.routes.images import upload_case_images
        from app.services.photo_service import PhotoService
        from app.services.project_service import ProjectService
        from app.storage.backend import UploadValidationError

        project = _make_project()
        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}
        mock_file = _make_upload_file("photo.jpg")
        mock_form = MagicMock()
        mock_form.multi_items = MagicMock(return_value=[("files", mock_file)])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(
            side_effect=UploadValidationError(
                "Content-Type mismatch: declared 'image/png' but actual image data is 'image/jpeg'.",
                status_code=415,
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_test",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 415
        assert "Content-Type mismatch" in exc_info.value.detail
