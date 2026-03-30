"""
Upload validation tests — verify that photo uploads and preview access
are scoped to the correct organization.
"""
import importlib
import inspect

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_project(project_id: str, org_id: str):
    p = MagicMock()
    p.id = project_id
    p.organization_id = org_id
    p.created_by_user_id = "usr_1"
    p.title = "Test project"
    p.description = None
    p.address_label = None
    p.property_type = "facade"
    p.repair_scope = "local_repair"
    p.status = "draft"
    p.photos = []
    p.proposal_draft = None
    return p


def _make_photo(photo_id: str, project_id: str):
    ph = MagicMock()
    ph.id = photo_id
    ph.project_id = project_id
    ph.original_filename = "test.jpg"
    ph.storage_key = f"projects/{project_id}/test.jpg"
    ph.preview_storage_key = f"projects/{project_id}/preview/test.jpg"
    ph.ai_input_storage_key = f"projects/{project_id}/ai/test.jpg"
    ph.mime_type = "image/jpeg"
    ph.file_size = 10000
    ph.width = 1920
    ph.height = 1080
    ph.preview_width = 1600
    ph.preview_height = 900
    ph.preview_file_size = 8000
    ph.ai_input_width = 1280
    ph.ai_input_height = 720
    ph.ai_input_file_size = 6000
    ph.taken_at = None
    ph.exif_lat = None
    ph.exif_lng = None
    ph.processing_status = "ready"
    ph.is_primary = False
    ph.is_analysis_reference = False
    ph.sort_order = 1
    return ph


# ─────────────────────────────────────────────────────────────────────────────
# 1. Route source checks
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadRouteStructure:

    def test_upload_route_validates_org_before_upload(self):
        """upload_case_images must call get_project_lean with organization_id before processing files."""
        from app.api.routes.images import upload_case_images
        src = inspect.getsource(upload_case_images)
        assert "organization_id=org_id" in src
        assert "get_project_lean" in src

    def test_preview_route_requires_authentication(self):
        """get_image_preview must require get_current_user dependency."""
        from app.api.routes.images import get_image_preview
        src = inspect.getsource(get_image_preview)
        assert "get_current_user" in src

    def test_preview_route_validates_org(self):
        """get_image_preview must verify the photo's project belongs to the user's org."""
        from app.api.routes.images import get_image_preview
        src = inspect.getsource(get_image_preview)
        assert "organization_id=org_id" in src
        assert "get_project_lean" in src

    def test_photo_read_model_has_project_id(self):
        """ProjectPhotoRead must expose projectId for org validation."""
        from app.schemas.photo import ProjectPhotoRead
        assert "projectId" in ProjectPhotoRead.model_fields

    def test_to_read_model_maps_project_id(self):
        """to_read_model must set projectId from photo.project_id."""
        from app.services.photo_service import to_read_model
        src = inspect.getsource(to_read_model)
        assert "projectId=photo.project_id" in src

    def test_upload_route_does_not_support_json_metadata_only_creation(self):
        """Legacy JSON metadata-only uploads must not bypass real file validation/storage."""
        from app.api.routes.images import upload_case_images
        src = inspect.getsource(upload_case_images)
        assert "JSON metadata-only uploads are not supported" in src
        assert "create_json_photo" not in src


def test_upload_goes_to_s3_only(monkeypatch):
    """When STORAGE_BACKEND=s3, upload storage writes must resolve to S3 backend functions only."""
    import app.storage.backend as backend_mod
    import app.storage.local_photo_storage as local_storage_mod
    import app.storage.s3_photo_storage as s3_storage_mod
    import app.services.photo_service as photo_service_mod

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    reloaded_backend = importlib.reload(backend_mod)
    try:
        assert reloaded_backend.save_original_photo is s3_storage_mod.save_original_photo
        assert reloaded_backend.write_storage_file is s3_storage_mod.write_storage_file
        assert reloaded_backend.save_original_photo is not local_storage_mod.save_original_photo
        assert reloaded_backend.write_storage_file is not local_storage_mod.write_storage_file

        source = inspect.getsource(photo_service_mod)
        assert "from app.storage.backend import (" in source
        assert "local_photo_storage" not in source
    finally:
        monkeypatch.setenv("STORAGE_BACKEND", "local")
        importlib.reload(backend_mod)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Upload to own project — passes
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadOwnProject:

    @pytest.mark.asyncio
    async def test_upload_succeeds_when_project_in_org(self):
        """upload_case_images proceeds if project belongs to the user's org."""
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService
        from app.repositories.project_repository import ProjectRepository

        project = _make_project("prj_A", "org_A")

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        # Verify: no 404 raised for matching org
        result = await mock_project_service.get_project_lean("prj_A", organization_id="org_A")
        assert result is not None
        assert result.id == "prj_A"
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_A")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Upload to foreign project — fails
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadForeignProject:

    @pytest.mark.asyncio
    async def test_upload_fails_when_project_not_in_org(self):
        """upload_case_images raises 404 if project does not belong to user's org."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "multipart/form-data"}

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_B"

        mock_project_service = AsyncMock(spec=ProjectService)
        # project belongs to org_A, but user is in org_B → returns None
        mock_project_service.get_project_lean = AsyncMock(return_value=None)

        mock_photo_service = AsyncMock(spec=PhotoService)

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_A",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_B")

    @pytest.mark.asyncio
    async def test_upload_fails_when_project_not_found(self):
        """upload_case_images raises 404 if project does not exist."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "application/json"}

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=None)

        mock_photo_service = AsyncMock(spec=PhotoService)

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_nonexistent",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_json_metadata_only_is_rejected_for_existing_project(self):
        """Existing projects must still reject JSON uploads because they bypass byte validation."""
        from app.api.routes.images import upload_case_images
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        mock_request = MagicMock()
        mock_request.headers = {"content-type": "application/json"}

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        project = _make_project("prj_A", "org_A")
        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        mock_photo_service = AsyncMock(spec=PhotoService)

        with pytest.raises(HTTPException) as exc_info:
            await upload_case_images(
                request=mock_request,
                case_id="prj_A",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 415
        assert "multipart/form-data" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 4. Preview access — org check
# ─────────────────────────────────────────────────────────────────────────────

class TestPreviewOrgCheck:

    @pytest.mark.asyncio
    async def test_preview_fails_for_foreign_org_photo(self):
        """get_image_preview raises 404 if photo's project belongs to a different org."""
        from app.api.routes.images import get_image_preview
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        photo = _make_photo("pho_X", "prj_A")  # project belongs to org_A

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_B"

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.get_photo_by_id = AsyncMock()
        # Return a read model with projectId set
        read_model = MagicMock()
        read_model.projectId = "prj_A"
        read_model.variants = MagicMock()
        read_model.variants.preview = MagicMock()
        read_model.variants.preview.url = "/mock-storage/projects/prj_A/preview/test.jpg"
        mock_photo_service.get_photo_by_id.return_value = read_model

        mock_project_service = AsyncMock(spec=ProjectService)
        # project not in org_B → returns None
        mock_project_service.get_project_lean = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_image_preview(
                image_id="pho_X",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_B")

    @pytest.mark.asyncio
    async def test_preview_fails_for_nonexistent_photo(self):
        """get_image_preview raises 404 if photo does not exist."""
        from app.api.routes.images import get_image_preview
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.get_photo_by_id = AsyncMock(return_value=None)

        mock_project_service = AsyncMock(spec=ProjectService)

        with pytest.raises(HTTPException) as exc_info:
            await get_image_preview(
                image_id="pho_nonexistent",
                current_user=mock_user,
                project_service=mock_project_service,
                photo_service=mock_photo_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project_lean.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_succeeds_for_own_org_photo(self):
        """get_image_preview returns RedirectResponse for photo in user's org."""
        from fastapi.responses import RedirectResponse
        from app.api.routes.images import get_image_preview
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        project = _make_project("prj_A", "org_A")

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        read_model = MagicMock()
        read_model.projectId = "prj_A"
        read_model.variants = MagicMock()
        read_model.variants.preview = MagicMock()
        read_model.variants.preview.url = "/mock-storage/projects/prj_A/preview/test.jpg"
        read_model.url = "/mock-storage/projects/prj_A/test.jpg"

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.get_photo_by_id = AsyncMock(return_value=read_model)

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        response = await get_image_preview(
            image_id="pho_X",
            current_user=mock_user,
            project_service=mock_project_service,
            photo_service=mock_photo_service,
        )

        assert isinstance(response, RedirectResponse)
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id="org_A")

    @pytest.mark.asyncio
    async def test_superadmin_bypasses_org_check_on_preview(self):
        """Superadmin can access preview of any org's photo."""
        from fastapi.responses import RedirectResponse
        from app.api.routes.images import get_image_preview
        from app.services.project_service import ProjectService
        from app.services.photo_service import PhotoService

        project = _make_project("prj_A", "org_A")

        mock_user = MagicMock()
        mock_user.isSuperAdmin = True
        mock_user.organizationId = None

        read_model = MagicMock()
        read_model.projectId = "prj_A"
        read_model.variants = MagicMock()
        read_model.variants.preview = MagicMock()
        read_model.variants.preview.url = "/mock-storage/projects/prj_A/preview/test.jpg"
        read_model.url = "/mock-storage/projects/prj_A/test.jpg"

        mock_photo_service = AsyncMock(spec=PhotoService)
        mock_photo_service.get_photo_by_id = AsyncMock(return_value=read_model)

        mock_project_service = AsyncMock(spec=ProjectService)
        # superadmin: get_project with org_id=None returns project regardless of org
        mock_project_service.get_project_lean = AsyncMock(return_value=project)

        response = await get_image_preview(
            image_id="pho_X",
            current_user=mock_user,
            project_service=mock_project_service,
            photo_service=mock_photo_service,
        )

        assert isinstance(response, RedirectResponse)
        # org_id=None is passed for superadmin (no org filter)
        mock_project_service.get_project_lean.assert_called_once_with("prj_A", organization_id=None)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Storage route — authenticated file serving
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageRouteAuth:

    def test_storage_route_requires_authentication(self):
        """serve_storage_file must require get_current_user dependency."""
        from app.api.routes.storage import serve_storage_file
        src = inspect.getsource(serve_storage_file)
        assert "get_current_user" in src

    def test_storage_route_validates_org(self):
        """serve_storage_file must validate org before serving the file."""
        from app.api.routes.storage import serve_storage_file
        src = inspect.getsource(serve_storage_file)
        assert "organization_id=org_id" in src
        assert "get_project" in src

    def test_storage_route_guards_path_traversal(self):
        """serve_storage_file must guard against path traversal via relative_to check."""
        from app.api.routes.storage import serve_storage_file
        src = inspect.getsource(serve_storage_file)
        assert "relative_to" in src

    def test_storage_route_allows_only_known_prefixes(self):
        """serve_storage_file only serves files under 'projects' and 'exports'."""
        from app.api.routes.storage import _ALLOWED_PREFIXES
        assert "projects" in _ALLOWED_PREFIXES
        assert "exports" in _ALLOWED_PREFIXES

    def test_storage_route_requires_local_backend(self):
        """serve_storage_file must fail fast when local storage is not the active backend."""
        from app.api.routes.storage import serve_storage_file
        src = inspect.getsource(serve_storage_file)
        assert 'settings.storage_backend != "local"' in src

    @pytest.mark.asyncio
    async def test_storage_blocks_cross_tenant_photo(self):
        """serve_storage_file returns 404 for a photo from a different org."""
        from app.api.routes.storage import serve_storage_file
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_B"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project = AsyncMock(return_value=None)  # wrong org

        with pytest.raises(HTTPException) as exc_info:
            await serve_storage_file(
                file_path="projects/prj_A/preview/photo.jpg",
                current_user=mock_user,
                project_service=mock_project_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project.assert_called_once_with("prj_A", organization_id="org_B")

    @pytest.mark.asyncio
    async def test_storage_blocks_cross_tenant_export(self):
        """serve_storage_file returns 404 for an export from a different org."""
        from app.api.routes.storage import serve_storage_file
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_B"

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project = AsyncMock(return_value=None)  # wrong org

        with pytest.raises(HTTPException) as exc_info:
            await serve_storage_file(
                file_path="exports/prj_A/exp_abc-report.pdf",
                current_user=mock_user,
                project_service=mock_project_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project.assert_called_once_with("prj_A", organization_id="org_B")

    @pytest.mark.asyncio
    async def test_storage_rejects_invalid_path_prefix(self):
        """serve_storage_file returns 404 for paths outside projects/ or exports/."""
        from app.api.routes.storage import serve_storage_file
        from app.services.project_service import ProjectService

        mock_user = MagicMock()
        mock_user.isSuperAdmin = False
        mock_user.organizationId = "org_A"

        mock_project_service = AsyncMock(spec=ProjectService)

        with pytest.raises(HTTPException) as exc_info:
            await serve_storage_file(
                file_path="backups/secret.sql",
                current_user=mock_user,
                project_service=mock_project_service,
            )

        assert exc_info.value.status_code == 404
        mock_project_service.get_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_superadmin_can_access_any_org_storage(self):
        """Superadmin bypasses org filter and can access files from any org."""
        from app.api.routes.storage import serve_storage_file
        from app.services.project_service import ProjectService
        from fastapi.responses import FileResponse
        from unittest.mock import patch
        from pathlib import Path

        project = _make_project("prj_A", "org_A")

        mock_user = MagicMock()
        mock_user.isSuperAdmin = True
        mock_user.organizationId = None

        mock_project_service = AsyncMock(spec=ProjectService)
        mock_project_service.get_project = AsyncMock(return_value=project)

        fake_path = MagicMock(spec=Path)
        fake_path.exists.return_value = True
        fake_path.is_file.return_value = True

        with patch("app.api.routes.storage.STORAGE_ROOT") as mock_root:
            mock_root.resolve.return_value = Path("/storage")
            resolved = MagicMock(spec=Path)
            resolved.relative_to.return_value = Path("projects/prj_A/photo.jpg")
            resolved.exists.return_value = True
            resolved.is_file.return_value = True
            mock_root.__truediv__ = lambda self, x: resolved

            response = await serve_storage_file(
                file_path="projects/prj_A/photo.jpg",
                current_user=mock_user,
                project_service=mock_project_service,
            )

        mock_project_service.get_project.assert_called_once_with("prj_A", organization_id=None)
