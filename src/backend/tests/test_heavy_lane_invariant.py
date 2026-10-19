"""Heavy-lane invariant tests.

Invariant: the API MUST NOT perform heavy CPU/I/O work inline.
Every export and photo-processing request MUST be rejected with 503 when
``worker_heavy_concurrency == 0`` (no heavy-lane worker configured).

Coverage
--------
1.  require_worker_capacity raises 503 when worker_heavy_concurrency == 0
2.  require_worker_capacity passes when worker_heavy_concurrency > 0
3.  Export (quote-docx) → 503 when heavy lane disabled
4.  Export (proposal-docx) → 503 when heavy lane disabled
5.  Export (quote-pdf) → 503 when heavy lane disabled
6.  Export (case-zip) → 503 when heavy lane disabled
7.  Photo upload → 503 when heavy lane disabled
8.  Export (quote-docx) → enqueue called when lane is active
9.  Photo upload → enqueue called when lane is active
10. No inline heavy work is present in export_service or photo_service
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(*, heavy_concurrency: int = 0, analysis_queue_max_depth: int = 50,
               heavy_queue_max_depth: int = 50, backpressure_max_queued_jobs: int = 1000,
               backpressure_max_concurrent_jobs: int = 4,
               worker_concurrency: int = 2):
    return SimpleNamespace(
        worker_heavy_concurrency=heavy_concurrency,
        worker_concurrency=worker_concurrency,
        analysis_queue_max_depth=analysis_queue_max_depth,
        heavy_queue_max_depth=heavy_queue_max_depth,
        backpressure_max_queued_jobs=backpressure_max_queued_jobs,
        backpressure_max_concurrent_jobs=backpressure_max_concurrent_jobs,
        max_upload_size_mb=20,
        export_ttl_days=7,
    )


def _ready_backpressure_snapshot(settings):
    from app.core.backpressure import BackpressureSnapshot
    return BackpressureSnapshot(
        runtime_state="ready",
        analysis_queued=0,
        analysis_processing=0,
        heavy_queued=0,
        heavy_processing=0,
        retry_inflight=0,
        max_concurrent_jobs=settings.backpressure_max_concurrent_jobs,
        max_queued_jobs=settings.backpressure_max_queued_jobs,
        max_retry_inflight=100,
    )


def _case_detail(*, has_final_proposal: bool = True, has_proposal_draft: bool = True):
    photos = []
    ns = SimpleNamespace(
        id="prj_001",
        title="Test Case",
        organization_id="org_001",
        photos=photos,
        finalProposal=SimpleNamespace(subject="Nabídka") if has_final_proposal else None,
        proposalDraft=SimpleNamespace(subject="Návrh") if has_proposal_draft else None,
    )
    return ns


# ---------------------------------------------------------------------------
# 1–2. require_worker_capacity unit tests
# ---------------------------------------------------------------------------

class TestRequireWorkerCapacity:
    def test_raises_503_when_heavy_concurrency_is_zero(self):
        from app.core.backpressure import require_worker_capacity

        with pytest.raises(HTTPException) as exc_info:
            require_worker_capacity("test_surface", settings=_settings(heavy_concurrency=0))

        assert exc_info.value.status_code == 503

    def test_passes_when_heavy_concurrency_is_positive(self):
        from app.core.backpressure import require_worker_capacity

        # Must not raise
        require_worker_capacity("test_surface", settings=_settings(heavy_concurrency=2))

    def test_error_detail_mentions_worker(self):
        from app.core.backpressure import require_worker_capacity

        with pytest.raises(HTTPException) as exc_info:
            require_worker_capacity("test_surface", settings=_settings(heavy_concurrency=0))

        assert "worker" in exc_info.value.detail.lower() or "unavailable" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# 3–6. Export service → 503 when heavy lane disabled
# ---------------------------------------------------------------------------

class TestExportHeavyLaneDisabled:
    """All export methods must raise 503 when worker_heavy_concurrency == 0."""

    def _make_service(self):
        from app.services.export_service import ExportService
        repo = MagicMock()
        service = ExportService(repository=repo, work_queue=MagicMock())
        return service

    @pytest.mark.asyncio
    async def test_quote_docx_raises_503_when_lane_disabled(self):
        service = self._make_service()
        settings_stub = _settings(heavy_concurrency=0)

        with (
            patch("app.services.export_service.get_settings", return_value=settings_stub),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_quote_docx_export(case_detail=_case_detail())

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_quote_docx_precondition_beats_lane_503(self):
        service = self._make_service()
        settings_stub = _settings(heavy_concurrency=0)

        with patch("app.services.export_service.get_settings", return_value=settings_stub):
            with pytest.raises(ValueError, match="Final proposal is required"):
                await service.create_quote_docx_export(case_detail=_case_detail(has_final_proposal=False))

    @pytest.mark.asyncio
    async def test_proposal_docx_raises_503_when_lane_disabled(self):
        service = self._make_service()
        settings_stub = _settings(heavy_concurrency=0)

        with (
            patch("app.services.export_service.get_settings", return_value=settings_stub),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_proposal_docx_export(case_detail=_case_detail())

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_quote_pdf_raises_503_when_lane_disabled(self):
        service = self._make_service()
        settings_stub = _settings(heavy_concurrency=0)

        with (
            patch("app.services.export_service.get_settings", return_value=settings_stub),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_quote_pdf_export(case_detail=_case_detail())

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_case_zip_raises_503_when_lane_disabled(self):
        service = self._make_service()
        settings_stub = _settings(heavy_concurrency=0)

        with (
            patch("app.services.export_service.get_settings", return_value=settings_stub),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_case_zip_export(case_detail=_case_detail())

        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# 7. Photo upload → 503 when heavy lane disabled
# ---------------------------------------------------------------------------

class TestPhotoUploadHeavyLaneDisabled:
    @pytest.mark.asyncio
    async def test_photo_upload_raises_503_when_lane_disabled_before_persistence(self):
        """Valid uploads must fail closed before storage persistence when heavy lane is unavailable."""
        from app.services.photo_service import PhotoService

        repo = MagicMock()
        service = PhotoService(repository=repo, work_queue=MagicMock())
        settings_stub = _settings(heavy_concurrency=0)
        project = SimpleNamespace(id="prj_001", organization_id="org_001")
        mock_upload = MagicMock()
        mock_upload.filename = "photo.jpg"
        mock_upload.content_type = "image/jpeg"
        validated = SimpleNamespace(
            content=b"fake_image_bytes",
            actual_mime_type="image/jpeg",
            file_size=1024,
            original_filename="photo.jpg",
            storage_filename="photo.jpg",
            filename_was_missing=False,
            content_type_was_missing=False,
        )

        with (
            patch("app.services.photo_service.get_settings", return_value=settings_stub),
            patch("app.services.photo_service.validate_photo_upload", new=AsyncMock(return_value=validated)),
            patch("app.services.photo_service.save_original_photo", new=AsyncMock()) as mock_save_original,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_multipart_photo(project, mock_upload, is_primary=False)

        assert exc_info.value.status_code == 503
        mock_save_original.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_photo_upload_validation_is_not_masked_when_lane_disabled(self):
        """Invalid filename/path guards must beat 503 heavy-lane unavailability."""
        from app.services.photo_service import PhotoService

        service = PhotoService(repository=MagicMock(), work_queue=MagicMock())
        settings_stub = _settings(heavy_concurrency=0)
        mock_upload = MagicMock()
        mock_upload.filename = "../../etc/passwd"
        mock_upload.content_type = "image/jpeg"
        mock_upload.read = AsyncMock(return_value=b"unused")

        with patch("app.services.photo_service.get_settings", return_value=settings_stub):
            with pytest.raises(ValueError, match="path traversal"):
                await service.create_multipart_photo(
                    SimpleNamespace(id="prj_001", organization_id="org_001"),
                    mock_upload,
                    is_primary=False,
                )


# ---------------------------------------------------------------------------
# 8. Export → enqueue called when lane is active
# ---------------------------------------------------------------------------

class TestExportEnqueuesWhenLaneActive:
    @pytest.mark.asyncio
    async def test_quote_docx_enqueues_when_lane_active(self):
        from app.services.export_service import ExportService

        repo = MagicMock()
        pending_export = SimpleNamespace(
            id="exp_001",
            project_id="prj_001",
            export_type="quote-docx",
            file_name="nabidka.docx",
            status="pending",
            storage_key=None,
            expires_at=None,
            completed_at=None,
            created_at=None,
        )
        repo.create = AsyncMock(return_value=pending_export)
        repo.update_state = AsyncMock(return_value=pending_export)
        service = ExportService(repository=repo, work_queue=MagicMock())
        settings_stub = _settings(heavy_concurrency=2)
        snapshot = _ready_backpressure_snapshot(settings_stub)

        with (
            patch("app.services.export_service.get_settings", return_value=settings_stub),
            patch("app.services.export_service.collect_backpressure_snapshot", new=AsyncMock(return_value=snapshot)),
            patch("app.services.export_service.ensure_heavy_intake_capacity"),
            patch("app.services.export_service.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
            patch("app.services.export_service._to_export_read", return_value=MagicMock()),
        ):
            await service.create_quote_docx_export(case_detail=_case_detail())

        mock_enqueue.assert_awaited_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs.get("job_type") == "export_generate" or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == "export_generate"
        )


# ---------------------------------------------------------------------------
# 9. Photo upload → enqueue called when lane is active
# ---------------------------------------------------------------------------

class TestPhotoEnqueuesWhenLaneActive:
    @pytest.mark.asyncio
    async def test_photo_upload_enqueues_when_lane_active(self):
        from app.services.photo_service import PhotoService

        repo = MagicMock()
        created_photo = SimpleNamespace(
            id="pho_001",
            project_id="prj_001",
            processing_status="uploaded",
            storage_key="originals/prj_001/photo.jpg",
        )
        repo.count_photos = AsyncMock(return_value=1)
        repo.clear_primary = AsyncMock()
        repo.add_photo = AsyncMock(return_value=created_photo)
        repo.get_next_sort_order = AsyncMock(return_value=1)
        repo.update_photo = AsyncMock(return_value=created_photo)

        service = PhotoService(repository=repo, work_queue=MagicMock())
        settings_stub = _settings(heavy_concurrency=2)
        project = SimpleNamespace(id="prj_001", organization_id="org_001")

        mock_upload = MagicMock()
        mock_upload.filename = "photo.jpg"
        mock_upload.content_type = "image/jpeg"

        validated = SimpleNamespace(
            content=b"fake_image_bytes",
            actual_mime_type="image/jpeg",
            file_size=1024,
            original_filename="photo.jpg",
            storage_filename="photo.jpg",
            filename_was_missing=False,
            content_type_was_missing=False,
        )

        with (
            patch("app.services.photo_service.get_settings", return_value=settings_stub),
            patch("app.services.photo_service.validate_photo_upload", new=AsyncMock(return_value=validated)),
            patch("app.services.photo_service.get_image_dimensions", return_value=(1920, 1080)),
            patch("app.services.photo_service.save_original_photo", new=AsyncMock(return_value=("key/path.jpg", 1024))),
            patch("app.services.photo_service.build_derived_variants", return_value={
                "preview_storage_key": "k/p.jpg", "preview_file_size": 100,
                "preview_width": 800, "preview_height": 600,
                "ai_input_storage_key": "k/a.jpg", "ai_input_file_size": 80,
                "ai_input_width": 640, "ai_input_height": 480,
            }),
            patch("app.services.photo_service.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
            patch("app.services.photo_service.to_read_model", return_value=MagicMock()),
        ):
            await service.create_multipart_photo(project, mock_upload, is_primary=False)

        mock_enqueue.assert_awaited_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs.get("job_type") == "photo_variant_processing"


# ---------------------------------------------------------------------------
# 10. No inline processing functions called during API path
# ---------------------------------------------------------------------------

class TestNoInlineHeavyWork:
    """Verify that the heavy-generation functions are NOT reachable from the
    API path by inspecting the call graph via source inspection."""

    def test_export_service_create_methods_do_not_call_build_bytes_directly(self):
        import inspect
        import app.services.export_service as svc_module

        heavy_functions = [
            "_build_docx_bytes",
            "_build_proposal_docx_bytes",
            "_build_pdf_bytes",
            "_build_case_zip_bytes",
        ]
        api_methods = [
            "create_quote_docx_export",
            "create_proposal_docx_export",
            "create_quote_pdf_export",
            "create_case_zip_export",
        ]

        svc_class = svc_module.ExportService
        for method_name in api_methods:
            method = getattr(svc_class, method_name)
            src = inspect.getsource(method)
            for heavy_fn in heavy_functions:
                assert heavy_fn not in src, (
                    f"{method_name} must not call {heavy_fn} inline — "
                    "all heavy work must go through the worker queue"
                )

    def test_photo_service_create_multipart_does_not_call_process_variants_inline(self):
        import inspect
        import app.services.photo_service as svc_module

        method = getattr(svc_module.PhotoService, "create_multipart_photo")
        src = inspect.getsource(method)
        assert "_process_multipart_photo_variants" not in src, (
            "create_multipart_photo must not call _process_multipart_photo_variants inline — "
            "all heavy work must go through the worker queue"
        )
