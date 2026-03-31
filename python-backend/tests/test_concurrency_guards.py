# =============================================================================
# Concurrency guard contracts — AnalysisService and PhotoService
#
# These are unit-level contract tests, not true concurrent race simulations.
# SQLite + aiosqlite serialise writes, so DB-level TOCTOU races cannot be
# reliably triggered in the test environment.  True concurrent safety requires
# either PostgreSQL with SELECT FOR UPDATE, or a DB-level unique constraint.
#
# What these tests DO guarantee:
#   - The in-process guards are present and fire correctly
#   - Removal of a guard will immediately break a named test
#   - The selection logic in _ensure_analysis_reference is correct
#
# KNOWN LIMITATIONS (not fixable without DB-level locking):
#   - create_job: TOCTOU between get_active_job_for_project() and
#     create_queued_job() — two concurrent callers can both see None and
#     each insert a separate job record.
#   - set_primary_photo / set_analysis_reference_photo: clear_* and
#     update_photo are separate transactions — a second concurrent caller
#     can observe stale state.
# =============================================================================
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.services.analysis_service import AnalysisService
from app.services.photo_service import PhotoService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_photo(*, is_reference=False, is_primary=False, status="ready"):
    p = MagicMock()
    p.is_analysis_reference = is_reference
    p.is_primary = is_primary
    p.processing_status = status
    return p


def _make_analysis_service(*, active_job=None, new_job=None):
    mock_repo = AsyncMock()
    mock_repo.get_active_job_for_project = AsyncMock(return_value=active_job)
    mock_repo.get_active_job_for_project_by_type = AsyncMock(return_value=active_job)
    mock_repo.count_active_jobs_for_organization = AsyncMock(return_value=0)
    mock_repo.create_queued_job = AsyncMock(return_value=new_job)
    return AnalysisService(
        repository=mock_repo,
        photo_repository=AsyncMock(),
        provider_key="mock",
    ), mock_repo


def _make_photo_service(photos):
    mock_repo = AsyncMock()
    mock_repo.list_photos_by_project_id = AsyncMock(return_value=photos)
    mock_repo.clear_analysis_reference = AsyncMock()
    mock_repo.clear_primary = AsyncMock()
    mock_repo.save_changes = AsyncMock()
    mock_repo.update_photo = AsyncMock(side_effect=lambda p: p)
    mock_repo.get_photo = AsyncMock(return_value=None)
    return PhotoService(repository=mock_repo), mock_repo


# ── AnalysisService.create_job — idempotency guard ────────────────────────────

class TestCreateJobIdempotency:
    """create_job must return an existing active job rather than inserting a duplicate."""

    @pytest.mark.asyncio
    async def test_returns_existing_queued_job(self):
        """Existing queued job: guard fires, create_queued_job is never called."""
        existing = MagicMock(id="job-existing", status="queued")
        service, repo = _make_analysis_service(active_job=existing)

        project = MagicMock(id="proj-1", organization_id="org-1")
        result = await service.create_job(project, user_id="usr-1")

        assert result.job is existing
        assert result.created_new is False
        repo.create_queued_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_existing_running_job(self):
        """A job already in 'running' state must also block creation."""
        existing = MagicMock(id="job-running", status="running")
        service, repo = _make_analysis_service(active_job=existing)

        project = MagicMock(id="proj-1", organization_id="org-1")
        result = await service.create_job(project, user_id="usr-1")

        assert result.job is existing
        assert result.created_new is False
        repo.create_queued_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_job_when_none_active(self):
        """No active job: create_queued_job is called and its result is returned."""
        new_job = MagicMock(id="job-new")
        service, repo = _make_analysis_service(active_job=None, new_job=new_job)

        project = MagicMock(id="proj-1", organization_id="org-1")
        result = await service.create_job(project, user_id="usr-1")

        assert result.job is new_job
        assert result.created_new is True
        repo.create_queued_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_user_id_to_create(self):
        """user_id must be forwarded to create_queued_job."""
        new_job = MagicMock(id="job-new")
        service, repo = _make_analysis_service(active_job=None, new_job=new_job)

        project = MagicMock(id="proj-1", organization_id="org-1")
        await service.create_job(project, user_id="usr-specific")

        _kwargs = repo.create_queued_job.call_args[1]
        assert _kwargs.get("user_id") == "usr-specific"

    @pytest.mark.asyncio
    async def test_rejects_new_job_when_tenant_active_limit_is_reached(self):
        new_job = MagicMock(id="job-new")
        service, repo = _make_analysis_service(active_job=None, new_job=new_job)
        repo.count_active_jobs_for_organization = AsyncMock(return_value=10)

        project = MagicMock(id="proj-1", organization_id="org-1")

        with patch("app.services.analysis_service.get_settings") as get_settings:
            get_settings.return_value.analysis_jobs_per_tenant_limit = 10
            with pytest.raises(HTTPException) as exc_info:
                await service.create_job(project, user_id="usr-1")

        assert exc_info.value.status_code == 429
        repo.create_queued_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_new_job_when_queue_capacity_precheck_is_full(self):
        new_job = MagicMock(id="job-new")
        service, repo = _make_analysis_service(active_job=None, new_job=new_job)
        project = MagicMock(id="proj-1", organization_id="org-1")

        with (
            patch("app.services.analysis_service.get_settings") as get_settings,
            patch(
                "app.services.analysis_service.get_analysis_job_queue_counts",
                new=AsyncMock(return_value=(1000, 0)),
            ),
        ):
            get_settings.return_value.analysis_jobs_per_tenant_limit = 10
            get_settings.return_value.analysis_queue_max_depth = 1000
            with pytest.raises(HTTPException) as exc_info:
                await service.create_job(project, user_id="usr-1", job_queue=AsyncMock())

        assert exc_info.value.status_code == 429
        repo.create_queued_job.assert_not_awaited()


# ── PhotoService._ensure_analysis_reference — idempotency ────────────────────

class TestEnsureAnalysisReference:
    """_ensure_analysis_reference must be a no-op when the invariant already holds,
    and must pick the correct candidate when it doesn't."""

    @pytest.mark.asyncio
    async def test_noop_when_reference_already_set(self):
        """Reference is already set — do not modify any photo."""
        photos = [_make_photo(is_reference=True)]
        service, repo = _make_photo_service(photos)

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_not_awaited()
        repo.save_changes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_project_has_no_photos(self):
        """Empty project — nothing to set."""
        service, repo = _make_photo_service([])

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_not_awaited()
        repo.save_changes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_no_ready_photos(self):
        """Photos exist but none are ready — do not assign a non-ready reference."""
        photos = [_make_photo(status="uploaded"), _make_photo(status="processing")]
        service, repo = _make_photo_service(photos)

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_not_awaited()
        repo.save_changes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sets_primary_photo_as_reference_when_none_set(self):
        """Primary photo wins the candidate selection over non-primary."""
        other = _make_photo(is_primary=False, is_reference=False)
        primary = _make_photo(is_primary=True, is_reference=False)
        service, repo = _make_photo_service([other, primary])

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_awaited_once_with("proj-1")
        assert primary.is_analysis_reference is True
        assert other.is_analysis_reference is False
        repo.save_changes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sets_first_ready_photo_when_no_primary(self):
        """No primary exists — fall back to the first ready photo in the list."""
        first = _make_photo(is_primary=False, is_reference=False)
        second = _make_photo(is_primary=False, is_reference=False)
        service, repo = _make_photo_service([first, second])

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_awaited_once_with("proj-1")
        assert first.is_analysis_reference is True
        assert second.is_analysis_reference is False
        repo.save_changes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_ready_photos_for_candidate_selection(self):
        """A non-ready primary must not be chosen; fallback is the first ready photo."""
        non_ready_primary = _make_photo(is_primary=True, is_reference=False, status="failed")
        ready_other = _make_photo(is_primary=False, is_reference=False, status="ready")
        service, repo = _make_photo_service([non_ready_primary, ready_other])

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_awaited_once_with("proj-1")
        assert ready_other.is_analysis_reference is True
        assert non_ready_primary.is_analysis_reference is False

    @pytest.mark.asyncio
    async def test_idempotent_second_call_is_noop(self):
        """After the reference is set by the first call, a second call must be a no-op."""
        photo = _make_photo(is_primary=True, is_reference=False)
        service, repo = _make_photo_service([photo])

        # First call sets the reference
        await service._ensure_analysis_reference("proj-1")
        assert photo.is_analysis_reference is True

        # Second call — list_photos now returns the photo with reference=True
        repo.list_photos_by_project_id = AsyncMock(return_value=[photo])
        repo.clear_analysis_reference.reset_mock()
        repo.save_changes.reset_mock()

        await service._ensure_analysis_reference("proj-1")

        repo.clear_analysis_reference.assert_not_awaited()
        repo.save_changes.assert_not_awaited()


# ── PhotoService.set_primary_photo — sequential contract ─────────────────────

class TestSetPrimaryPhotoContract:
    """set_primary_photo must always clear all primaries before marking the target."""

    @pytest.mark.asyncio
    async def test_clear_primary_called_before_set(self):
        """clear_primary must be awaited before the photo is marked primary."""
        photo_b = MagicMock(id="pho-b", is_primary=False)

        service, repo = _make_photo_service([])
        repo.get_photo = AsyncMock(return_value=photo_b)
        repo.update_photo = AsyncMock(return_value=photo_b)

        with patch("app.services.photo_service.to_read_model", return_value=MagicMock()):
            await service.set_primary_photo("proj-1", "pho-b")

        repo.clear_primary.assert_awaited_once_with("proj-1")
        assert photo_b.is_primary is True

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_photo(self):
        """Missing photo must return None without touching any other state."""
        service, repo = _make_photo_service([])
        repo.get_photo = AsyncMock(return_value=None)

        result = await service.set_primary_photo("proj-1", "no-such-photo")

        assert result is None
        repo.clear_primary.assert_not_awaited()


# ── PhotoService.set_analysis_reference_photo — sequential contract ───────────

class TestSetAnalysisReferenceContract:
    """set_analysis_reference_photo must reject non-ready photos and clear before setting."""

    @pytest.mark.asyncio
    async def test_clears_before_setting_reference(self):
        """clear_analysis_reference must be called before marking the new reference."""
        photo = MagicMock(id="pho-ready", is_analysis_reference=False, processing_status="ready")

        service, repo = _make_photo_service([])
        repo.get_photo = AsyncMock(return_value=photo)
        repo.update_photo = AsyncMock(return_value=photo)

        with patch("app.services.photo_service.to_read_model", return_value=MagicMock()):
            await service.set_analysis_reference_photo("proj-1", "pho-ready")

        repo.clear_analysis_reference.assert_awaited_once_with("proj-1")
        assert photo.is_analysis_reference is True

    @pytest.mark.asyncio
    async def test_rejects_non_ready_photo(self):
        """A photo not in 'ready' state must raise ValueError without any DB writes."""
        photo = MagicMock(id="pho-uploaded", processing_status="uploaded")

        service, repo = _make_photo_service([])
        repo.get_photo = AsyncMock(return_value=photo)

        with pytest.raises(ValueError, match="ready"):
            await service.set_analysis_reference_photo("proj-1", "pho-uploaded")

        repo.clear_analysis_reference.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_photo(self):
        service, repo = _make_photo_service([])
        repo.get_photo = AsyncMock(return_value=None)

        result = await service.set_analysis_reference_photo("proj-1", "no-such-photo")

        assert result is None
        repo.clear_analysis_reference.assert_not_awaited()
