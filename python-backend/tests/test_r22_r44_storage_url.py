"""R-22 + R-44: Public URL generation must go through storage layer, not hardcoded in services."""
from unittest.mock import MagicMock, patch

import app.storage.local_photo_storage as storage_mod
import app.services.photo_service as photo_svc_mod
import app.services.export_service as export_svc_mod


# ── get_public_url unit tests ─────────────────────────────────────────────────

class TestGetPublicUrl:

    def test_returns_mock_storage_prefix_for_local(self):
        """Local storage maps keys to /mock-storage/<key>."""
        url = storage_mod.get_public_url("projects/p1/photo.jpg")
        assert url == "/mock-storage/projects/p1/photo.jpg"

    def test_preserves_full_key_path(self):
        url = storage_mod.get_public_url("exports/case-123/exp_abc-report.pdf")
        assert url == "/mock-storage/exports/case-123/exp_abc-report.pdf"

    def test_does_not_double_slash(self):
        url = storage_mod.get_public_url("projects/x/y.jpg")
        assert "//" not in url


# ── photo_service.to_read_model uses get_public_url ──────────────────────────

class TestToReadModelUsesStorageUrl:

    def _make_photo(self, **kwargs):
        photo = MagicMock()
        photo.id = "pho_001"
        photo.project_id = "proj_001"
        photo.original_filename = "test.jpg"
        photo.storage_key = kwargs.get("storage_key", "projects/p/test.jpg")
        photo.preview_storage_key = kwargs.get("preview_storage_key", "projects/p/preview/test.jpg")
        photo.ai_input_storage_key = kwargs.get("ai_input_storage_key", "projects/p/ai/test.jpg")
        photo.mime_type = "image/jpeg"
        photo.file_size = 100_000
        photo.width = 800
        photo.height = 600
        photo.taken_at = None
        photo.exif_lat = None
        photo.exif_lng = None
        photo.processing_status = "ready"
        photo.is_primary = False
        photo.is_analysis_reference = False
        photo.sort_order = 1
        photo.preview_file_size = 50_000
        photo.preview_width = 800
        photo.preview_height = 600
        photo.ai_input_file_size = 30_000
        photo.ai_input_width = 640
        photo.ai_input_height = 480
        return photo

    def test_to_read_model_calls_get_public_url(self):
        """to_read_model must delegate URL generation to get_public_url."""
        photo = self._make_photo()
        with patch.object(photo_svc_mod, "get_public_url", wraps=storage_mod.get_public_url) as mock_gpu:
            result = photo_svc_mod.to_read_model(photo)
        # get_public_url must have been called (at minimum for original + two variants)
        assert mock_gpu.call_count >= 3

    def test_to_read_model_url_matches_get_public_url(self):
        """url field on result must equal what get_public_url returns for that key."""
        photo = self._make_photo(storage_key="projects/myproject/img.jpg")
        result = photo_svc_mod.to_read_model(photo)
        expected = storage_mod.get_public_url("projects/myproject/img.jpg")
        assert result.url == expected

    def test_to_read_model_no_hardcoded_mock_storage_in_service_source(self):
        """Service source must not contain hardcoded /mock-storage/ URL assembly."""
        import inspect
        source = inspect.getsource(photo_svc_mod.to_read_model)
        assert '"/mock-storage/' not in source
        assert "f\"/mock-storage/" not in source

    def test_preview_url_none_when_no_preview_key(self):
        """Preview URL must be None when preview_storage_key is absent."""
        photo = self._make_photo(preview_storage_key=None)
        result = photo_svc_mod.to_read_model(photo)
        assert result.variants.preview.url is None


# ── export_service uses get_public_url ───────────────────────────────────────

class TestExportServiceUsesStorageUrl:

    def test_export_from_file_uses_get_public_url(self):
        """_export_from_file download URL must come from get_public_url."""
        from pathlib import Path
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case-001"
            case_dir.mkdir()
            export_id = "exp_abc12345"
            file_name = f"{export_id}-report.pdf"
            export_file = case_dir / file_name
            export_file.write_bytes(b"%PDF-1.4 test")

            with patch.object(export_svc_mod, "get_public_url", wraps=storage_mod.get_public_url) as mock_gpu:
                result = export_svc_mod._export_from_file(export_id, export_file)

            mock_gpu.assert_called_once()
            assert result.downloadUrl.startswith("/mock-storage/")

    def test_export_service_source_no_hardcoded_mock_storage(self):
        """ExportService methods must not hardcode /mock-storage/ URL strings."""
        import inspect
        source = inspect.getsource(export_svc_mod.ExportService)
        assert '"/mock-storage/' not in source
        assert "f\"/mock-storage/" not in source
