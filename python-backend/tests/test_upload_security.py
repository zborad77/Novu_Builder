# =============================================================================
# Upload security guard tests
#
# Covers guards added to PhotoService.create_multipart_photo:
#   1. Path traversal rejection  — ".." in filename
#   2. Extension whitelist       — only .jpg/.jpeg/.png/.webp accepted
#
# Magic-bytes validation and file-size limits are covered in
# test_upload_size_limit.py and are not duplicated here.
# =============================================================================
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, UploadFile


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_upload_file(filename: str, content: bytes = b"x" * 100) -> MagicMock:
    f = MagicMock(spec=UploadFile)
    f.filename = filename
    f.content_type = "image/jpeg"
    f.size = None
    f.read = AsyncMock(return_value=content)
    return f


def _make_project(project_id: str = "prj_test") -> MagicMock:
    p = MagicMock()
    p.id = project_id
    p.organization_id = "org_test"
    return p


def _make_fake_settings(limit_mb: int = 20) -> MagicMock:
    s = MagicMock()
    s.max_upload_size_mb = limit_mb
    return s


# ── 1. Path traversal guard ───────────────────────────────────────────────────

class TestPathTraversalGuard:

    @pytest.mark.asyncio
    async def test_double_dot_in_filename_raises(self):
        """Filename containing '..' must be rejected before any bytes are read."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("../../etc/passwd")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path traversal"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_double_dot_in_subdirectory_raises(self):
        """Traversal attempt embedded in a path component is rejected."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("uploads/../secret.jpg")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path traversal"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_normal_filename_not_rejected(self):
        """A clean filename must not trigger the path-traversal guard."""
        from app.services.photo_service import PhotoService

        content = b"x" * (1 * 1024 * 1024)
        mock_file = _make_upload_file("photo.jpg", content)
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
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.save_original_photo", return_value=("projects/prj_test/photo.jpg", None)),
            patch("app.services.photo_service.validate_image_format"),
        ):
            result = await service.create_multipart_photo(project, mock_file, is_primary=True)

        assert result is not None

    @pytest.mark.asyncio
    async def test_route_returns_413_on_path_traversal(self):
        """Route must map path-traversal ValueError to HTTP 413."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

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
        mock_project_service.get_project = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.create_multipart_photo = AsyncMock(
            side_effect=ValueError("Invalid filename: path traversal sequences are not allowed.")
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
        assert "path traversal" in exc_info.value.detail


# ── 2. Extension whitelist guard ──────────────────────────────────────────────

class TestExtensionWhitelistGuard:

    @pytest.mark.asyncio
    async def test_exe_extension_rejected(self):
        """Files with .exe extension must be rejected before bytes are read."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("malware.exe")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="extension"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_php_extension_rejected(self):
        """Files with .php extension are rejected."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("shell.php")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="extension"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_gif_extension_rejected(self):
        """GIF extension is rejected at extension-check stage (before magic-bytes check)."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("animation.gif")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="extension"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_jpg_extension_passes_guard(self):
        """.jpg is allowed by the extension guard (magic bytes check follows)."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.jpg")
        project = _make_project()
        service = PhotoService(AsyncMock())

        # We only want to confirm the guard does NOT raise for .jpg;
        # validate_image_format will raise on synthetic bytes — that's fine.
        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_jpeg_extension_passes_guard(self):
        """.jpeg is allowed."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.jpeg")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_png_extension_passes_guard(self):
        """.png is allowed."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.png")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_webp_extension_passes_guard(self):
        """.webp is allowed."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("photo.webp")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_extension_check_is_case_insensitive(self):
        """.JPG (uppercase) must be treated as .jpg and allowed."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("PHOTO.JPG")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_no_extension_passes_guard(self):
        """A filename with no extension does not trigger the whitelist guard
        (handled downstream by magic-bytes check)."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("imagefile")
        project = _make_project()
        service = PhotoService(AsyncMock())

        with (
            patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()),
            patch("app.services.photo_service.validate_image_format"),
            patch("app.services.photo_service.save_original_photo", side_effect=RuntimeError("stop here")),
        ):
            with pytest.raises(RuntimeError, match="stop here"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

    @pytest.mark.asyncio
    async def test_route_returns_413_on_bad_extension(self):
        """Route must map bad-extension ValueError to HTTP 413."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        project = _make_project()

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data; boundary=----"}
        mock_file = _make_upload_file("virus.exe")
        mock_form = MagicMock()
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
            side_effect=ValueError("Unsupported file extension '.exe': only JPEG, PNG, and WEBP files are accepted.")
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
        assert "extension" in exc_info.value.detail


# ── 3. Guard order: path traversal checked before Content-Length ───────────────

class TestGuardOrdering:

    @pytest.mark.asyncio
    async def test_path_traversal_checked_before_size(self):
        """Path traversal guard fires before any byte is read (even if size is fine)."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("../../photo.jpg", content=b"x" * 100)
        mock_file.size = 100  # well within any limit
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="path traversal"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

        mock_file.read.assert_not_called()

    @pytest.mark.asyncio
    async def test_extension_checked_before_bytes_read(self):
        """Extension guard fires before file.read() is awaited."""
        from app.services.photo_service import PhotoService

        mock_file = _make_upload_file("evil.exe", content=b"x" * 100)
        mock_file.size = 100
        project = _make_project()
        service = PhotoService(AsyncMock())

        with patch("app.services.photo_service.get_settings", return_value=_make_fake_settings()):
            with pytest.raises(ValueError, match="extension"):
                await service.create_multipart_photo(project, mock_file, is_primary=False)

        mock_file.read.assert_not_called()
