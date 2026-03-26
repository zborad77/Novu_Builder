"""
Upload size limit tests — verify that create_multipart_photo enforces
MAX_UPLOAD_SIZE_MB and that the route converts the error to HTTP 413.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, UploadFile


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_upload_file(content: bytes, filename: str = "photo.jpg") -> MagicMock:
    """Return a mock UploadFile that yields the given content on read()."""
    f = MagicMock(spec=UploadFile)
    f.filename = filename
    f.content_type = "image/jpeg"
    f.read = AsyncMock(return_value=content)
    return f


def _make_project(project_id: str = "prj_test") -> MagicMock:
    p = MagicMock()
    p.id = project_id
    p.organization_id = "org_test"
    return p


def _make_fake_settings(limit_mb: int):
    s = MagicMock()
    s.max_upload_size_mb = limit_mb
    return s


# ─────────────────────────────────────────────────────────────────────────────
# 1. Service-level guard
# ─────────────────────────────────────────────────────────────────────────────

class TestPhotoServiceSizeGuard:

    @pytest.mark.asyncio
    async def test_file_within_limit_proceeds(self):
        """create_multipart_photo does not raise when content fits the limit."""
        from app.services.photo_service import PhotoService

        content = b"x" * (5 * 1024 * 1024)  # 5 MB
        mock_file = _make_upload_file(content)
        project = _make_project()

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=0)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=1)
        mock_repo.add_photo = AsyncMock(return_value=MagicMock(
            id="pho_1", project_id=project.id, original_filename="photo.jpg",
            storage_key="projects/prj_test/photo.jpg",
            mime_type="image/jpeg", file_size=len(content),
            width=None, height=None,
            preview_storage_key=None, preview_file_size=None,
            preview_width=None, preview_height=None,
            ai_input_storage_key=None, ai_input_file_size=None,
            ai_input_width=None, ai_input_height=None,
            processing_status="uploaded",
            taken_at=None, exif_lat=None, exif_lng=None,
            is_primary=True, is_analysis_reference=True, sort_order=1,
        ))
        mock_repo.update_photo = AsyncMock(side_effect=lambda p: p)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings(20)),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
            patch("app.services.photo_service.write_storage_file"),
        ):
            # Should not raise
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result is not None

    @pytest.mark.asyncio
    async def test_file_over_limit_raises_value_error(self):
        """create_multipart_photo raises ValueError when content exceeds the limit."""
        from app.services.photo_service import PhotoService

        limit_mb = 10
        content = b"x" * (limit_mb * 1024 * 1024 + 1)  # 1 byte over
        mock_file = _make_upload_file(content)
        project = _make_project()

        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings(limit_mb)),
            patch("app.services.photo_service.save_original_photo"),
        ):
            with pytest.raises(ValueError, match="File too large"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_file_exactly_at_limit_proceeds(self):
        """create_multipart_photo allows content exactly equal to the limit."""
        from app.services.photo_service import PhotoService

        limit_mb = 10
        content = b"x" * (limit_mb * 1024 * 1024)  # exactly at limit
        mock_file = _make_upload_file(content)
        project = _make_project()

        mock_repo = AsyncMock()
        mock_repo.count_photos = AsyncMock(return_value=1)
        mock_repo.clear_primary = AsyncMock()
        mock_repo.get_next_sort_order = AsyncMock(return_value=2)
        mock_repo.add_photo = AsyncMock(return_value=MagicMock(
            id="pho_2", project_id=project.id, original_filename="photo.jpg",
            storage_key="projects/prj_test/photo.jpg",
            mime_type="image/jpeg", file_size=len(content),
            width=None, height=None,
            preview_storage_key=None, preview_file_size=None,
            preview_width=None, preview_height=None,
            ai_input_storage_key=None, ai_input_file_size=None,
            ai_input_width=None, ai_input_height=None,
            processing_status="uploaded",
            taken_at=None, exif_lat=None, exif_lng=None,
            is_primary=False, is_analysis_reference=False, sort_order=2,
        ))
        mock_repo.update_photo = AsyncMock(side_effect=lambda p: p)
        mock_repo.save_changes = AsyncMock()

        service = PhotoService(mock_repo)

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings(limit_mb)),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
            patch("app.services.photo_service.write_storage_file"),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=False)

        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Route-level: ValueError → HTTP 413
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadRouteSizeLimit:

    @pytest.mark.asyncio
    async def test_route_returns_413_on_oversize(self):
        """upload_case_images returns HTTP 413 when photo_service raises ValueError."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        project = _make_project()

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}

        mock_form = MagicMock()
        mock_file = _make_upload_file(b"x" * 1024)
        mock_form.multi_items = MagicMock(return_value=[("files", mock_file)])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(
            side_effect=ValueError("File too large: 21000000 bytes exceeds the 20 MB upload limit.")
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
        """upload_case_images returns 201 when photo_service succeeds."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService
        from app.schemas.photo import ProjectPhotoRead

        project = _make_project()

        _variant = {"storageKey": None, "fileSize": None, "width": None, "height": None, "url": None}
        photo_read = MagicMock(spec=ProjectPhotoRead)
        photo_read.id = "pho_ok"
        photo_read.storageKey = "projects/prj_test/photo.jpg"
        photo_read.isPrimary = True
        photo_read.processingStatus = "uploaded"
        photo_read.variants = {"original": _variant, "preview": _variant, "aiInput": _variant}

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}

        mock_form = MagicMock()
        mock_file = _make_upload_file(b"x" * 1024)
        mock_form.multi_items = MagicMock(return_value=[("files", mock_file)])
        mock_form.get = MagicMock(return_value="false")
        mock_request.form = AsyncMock(return_value=mock_form)

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_test"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project = AsyncMock(return_value=project)

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
