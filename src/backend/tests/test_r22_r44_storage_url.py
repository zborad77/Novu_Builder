"""Signed storage URL generation must stay inside the storage layer.

NC-007 kap. 6.3: API read modely (fotky, exporty) už podepsané URL úložiště
nevracejí – jen relativní cestu na streamovací endpoint core. Podepsané URL
zůstávají jen pro interní použití (AI pipeline, offer worker; F4.7).
"""

import inspect
import sys
import types
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.modules.exports.export_service as export_svc_mod
import app.modules.media.photo_service as photo_svc_mod
import app.platform.storage.local_photo_storage as local_storage_mod
import app.platform.storage.s3_photo_storage as s3_storage_mod


class TestLocalSignedUrl:
    def test_returns_mock_storage_prefix_for_local(self):
        url = local_storage_mod.generate_presigned_url("projects/p1/photo.jpg")
        assert url == "/mock-storage/projects/p1/photo.jpg"

    def test_preserves_full_key_path(self):
        url = local_storage_mod.generate_presigned_url("exports/case-123/exp_abc-report.pdf")
        assert url == "/mock-storage/exports/case-123/exp_abc-report.pdf"

    def test_ttl_above_max_is_rejected(self):
        try:
            local_storage_mod.generate_presigned_url("projects/x/y.jpg", expires=3601)
        except ValueError as exc:
            assert "between 1 and 3600" in str(exc)
        else:
            raise AssertionError("Expected ValueError for signed URL TTL above 1 hour.")


class TestPhotoServiceUsesFilesEndpoint:
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
        photo.processing_status = kwargs.get("processing_status", "ready")
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

    def test_to_read_model_never_signs_storage_urls(self):
        photo = self._make_photo()
        with patch.object(
            local_storage_mod,
            "generate_presigned_url",
            wraps=local_storage_mod.generate_presigned_url,
        ) as mock_presign:
            photo_svc_mod.to_read_model(photo)

        assert mock_presign.call_count == 0
        assert not hasattr(photo_svc_mod, "generate_presigned_url")

    def test_to_read_model_urls_point_to_the_files_endpoint(self):
        photo = self._make_photo(storage_key="projects/myproject/img.jpg")
        result = photo_svc_mod.to_read_model(photo)
        assert result.url == "/api/v1/files/images/pho_001/original"
        assert result.variants.original.url == "/api/v1/files/images/pho_001/original"
        assert result.variants.preview.url == "/api/v1/files/images/pho_001/preview"
        assert result.variants.aiInput.url == "/api/v1/files/images/pho_001/ai-input"

    def test_preview_url_none_when_no_preview_key(self):
        photo = self._make_photo(preview_storage_key=None)
        result = photo_svc_mod.to_read_model(photo)
        assert result.variants.preview.url is None

    def test_derived_urls_none_until_processing_is_ready(self):
        result = photo_svc_mod.to_read_model(self._make_photo(processing_status="processing"))
        assert result.url == "/api/v1/files/images/pho_001/original"
        assert result.variants.preview.url is None
        assert result.variants.aiInput.url is None

    def test_service_source_has_no_hardcoded_mock_storage(self):
        import inspect

        source = inspect.getsource(photo_svc_mod.to_read_model)
        assert '"/mock-storage/' not in source
        assert "generate_presigned_url" not in source


class TestExportServiceUsesFilesEndpoint:
    def _export(self, **overrides):
        values = dict(
            id="exp_abc12345",
            project_id="case-001",
            export_type="quote-pdf",
            status="completed",
            file_name="report.pdf",
            storage_key="exports/case-001/exp_abc12345-report.pdf",
            created_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
            completed_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
            expires_at=datetime(2026, 4, 6, 10, 0, tzinfo=UTC),
        )
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_to_export_read_points_to_the_files_endpoint(self):
        result = export_svc_mod._to_export_read(self._export())

        assert result.downloadUrl == "/api/v1/files/exports/exp_abc12345"
        assert result.storageKey == "exports/case-001/exp_abc12345-report.pdf"
        assert result.expiresAt == datetime(2026, 4, 6, 10, 0, tzinfo=UTC)
        assert not hasattr(export_svc_mod, "generate_presigned_url")

    def test_download_url_none_until_completed(self):
        result = export_svc_mod._to_export_read(self._export(status="pending", storage_key=None))
        assert result.downloadUrl is None

    def test_export_service_source_has_no_hardcoded_mock_storage(self):
        import inspect

        source = inspect.getsource(export_svc_mod.ExportService)
        assert '"/mock-storage/' not in source


class TestS3SignedUrl:
    def test_s3_generate_presigned_url_uses_bucket_key_and_ttl(self, monkeypatch):
        monkeypatch.setenv("S3_BUCKET", "novu-prod")
        monkeypatch.setenv("S3_REGION", "eu-central-1")
        monkeypatch.setenv("STORAGE_SIGNED_URL_TTL_SECONDS", "900")
        fake_client = MagicMock()
        fake_client.generate_presigned_url.return_value = "https://signed.example.test/object?sig=123"

        with patch.object(s3_storage_mod, "_get_s3_client", return_value=fake_client):
            result = s3_storage_mod.generate_presigned_url("projects/p1/photo.jpg")

        assert result.startswith("https://signed.example.test/")
        fake_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "novu-prod", "Key": "projects/p1/photo.jpg"},
            ExpiresIn=900,
        )

    def test_s3_client_kwargs_include_fail_fast_timeouts(self, monkeypatch):
        monkeypatch.setenv("S3_REGION", "eu-central-1")
        monkeypatch.setenv("S3_CONNECT_TIMEOUT_SECONDS", "2.5")
        monkeypatch.setenv("S3_READ_TIMEOUT_SECONDS", "8.0")
        monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.example.test")
        monkeypatch.setenv("S3_ACCESS_KEY_ID", "AKIA_TEST_KEY")
        monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test-secret-key")

        fake_botocore = types.ModuleType("botocore")
        fake_botocore_config = types.ModuleType("botocore.config")

        class FakeConfig:
            def __init__(self, **kwargs):
                self.connect_timeout = kwargs["connect_timeout"]
                self.read_timeout = kwargs["read_timeout"]
                self.retries = kwargs["retries"]

        fake_botocore_config.Config = FakeConfig

        with patch.dict(sys.modules, {"botocore": fake_botocore, "botocore.config": fake_botocore_config}):
            kwargs = s3_storage_mod._build_s3_client_kwargs()

        assert kwargs["region_name"] == "eu-central-1"
        assert kwargs["endpoint_url"] == "https://s3.example.test"
        assert kwargs["aws_access_key_id"] == "AKIA_TEST_KEY"
        assert kwargs["aws_secret_access_key"] == "test-secret-key"
        assert kwargs["config"].connect_timeout == 2.5
        assert kwargs["config"].read_timeout == 8.0


def test_read_models_expose_no_storage_url():
    """API read modely nesmí obsahovat URL úložiště (presigned S3, /mock-storage)."""
    photo = MagicMock()
    photo.id = "pho_001"
    photo.project_id = "proj_001"
    photo.original_filename = "test.jpg"
    photo.storage_key = "projects/proj_001/test.jpg"
    photo.preview_storage_key = "projects/proj_001/preview/test.jpg"
    photo.ai_input_storage_key = "projects/proj_001/ai/test.jpg"
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

    export = SimpleNamespace(
        id="exp_abc12345",
        project_id="case-001",
        export_type="quote-pdf",
        status="completed",
        file_name="report.pdf",
        storage_key="exports/case-001/exp_abc12345-report.pdf",
        created_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 30, 10, 0, tzinfo=UTC),
        expires_at=datetime(2026, 4, 6, 10, 0, tzinfo=UTC),
    )
    signed = "https://signed.example.test/object?X-Amz-Signature=abc"
    # I kdyby aktivní backend podepisoval (S3), read modely ho nevolají.
    with patch.object(local_storage_mod, "generate_presigned_url", return_value=signed):
        photo_dump = photo_svc_mod.to_read_model(photo).model_dump_json()
        export_dump = export_svc_mod._to_export_read(export).model_dump_json()

    for dump in (photo_dump, export_dump):
        for marker in ("X-Amz-", ":9000", "/mock-storage/", "https://"):
            assert marker not in dump

    photo_source = inspect.getsource(photo_svc_mod.to_read_model)
    export_source = inspect.getsource(export_svc_mod._to_export_read)
    for source in (photo_source, export_source):
        assert "get_public_url" not in source
        assert "generate_presigned_url" not in source
