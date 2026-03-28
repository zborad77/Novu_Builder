"""
Worker isolation tests — verify that background job processing
cannot access projects from a different organization.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import inspect
from fastapi import HTTPException

from app.services.analysis_service import _MAX_JOB_RETRY_COUNT


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
    return p


def _make_job(job_id: str, project_id: str):
    j = MagicMock()
    j.id = job_id
    j.project_id = project_id
    j.requested_by_user_id = "usr_1"
    j.retry_count = 0
    j.status = "queued"
    j.started_at = None
    j.finished_at = None
    j.error_message = None
    j.input_payload = None
    j.output_summary = None
    return j


# ─────────────────────────────────────────────────────────────────────────────
# 1. execute_job — worker processes project in correct organization
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteJobOrgScope:

    def test_execute_job_signature_has_organization_id(self):
        from app.services.analysis_service import AnalysisService
        sig = inspect.signature(AnalysisService.execute_job)
        assert "organization_id" in sig.parameters

    def test_execute_job_has_mismatch_guard(self):
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        assert "job.project_id != project_id" in src

    def test_execute_job_uses_org_scoped_fetch(self):
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        assert "get_project_in_org" in src

    @pytest.mark.asyncio
    async def test_execute_job_fails_on_project_mismatch(self):
        """If job.project_id != project_id, job is failed and HTTPException(403) is raised."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        job = _make_job("job_1", "prj_A")  # job belongs to prj_A
        session = AsyncMock()

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)

        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            with patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo), \
                 patch("app.services.analysis_service.PhotoRepository"):

                service = AnalysisService(
                    repository=AsyncMock(spec=AnalysisRepository),
                    photo_repository=AsyncMock(spec=PhotoRepository),
                    provider_key="mock",
                )
                # Call with project_id "prj_B" but job.project_id is "prj_A"
                with pytest.raises(HTTPException) as exc_info:
                    await service.execute_job("job_1", "prj_B", organization_id="org_A")

        assert exc_info.value.status_code == 403
        assert job.status == "failed"
        assert "prj_A" in job.error_message
        assert "prj_B" in job.error_message

    @pytest.mark.asyncio
    async def test_execute_job_fails_when_project_not_in_org(self):
        """If project does not belong to the given org, job is failed and HTTPException(403) is raised."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        job = _make_job("job_1", "prj_A")
        session = AsyncMock()

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        # get_project_in_org returns None — project not in org_B
        mock_repo.get_project_in_org = AsyncMock(return_value=None)

        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            with patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo), \
                 patch("app.services.analysis_service.PhotoRepository"):

                service = AnalysisService(
                    repository=AsyncMock(spec=AnalysisRepository),
                    photo_repository=AsyncMock(spec=PhotoRepository),
                    provider_key="mock",
                )
                with pytest.raises(HTTPException) as exc_info:
                    await service.execute_job("job_1", "prj_A", organization_id="org_B")

        assert exc_info.value.status_code == 403
        assert job.status == "failed"
        assert "Project not found" in job.error_message


# ─────────────────────────────────────────────────────────────────────────────
# 2. execute_job — cannot load project from different organization
# ─────────────────────────────────────────────────────────────────────────────

class TestExecuteJobCrossTenantBlocked:

    def test_execute_job_does_not_use_raw_session_get_when_org_provided(self):
        """When organization_id is given, execute_job must use get_project_in_org, not session.get."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        # The org-scoped branch calls get_project_in_org
        assert "get_project_in_org(project_id, organization_id)" in src
        # session.get(Project is only used in the else branch
        # Verify it's conditional on organization_id being None
        assert "if organization_id is not None:" in src

    @pytest.mark.asyncio
    async def test_org_scoped_project_fetch_is_called_with_correct_args(self):
        """execute_job calls get_project_in_org with project_id and organization_id."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        job = _make_job("job_1", "prj_A")
        project = _make_project("prj_A", "org_A")
        session = AsyncMock()

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_repo.get_project_in_org = AsyncMock(return_value=project)
        mock_photo_repo = AsyncMock(spec=PhotoRepository)
        mock_photo_repo.list_photos_by_project_id = AsyncMock(return_value=[])

        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory, \
             patch("app.services.analysis_service.run_project_analysis") as mock_analysis, \
             patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo), \
             patch("app.services.analysis_service.PhotoRepository", return_value=mock_photo_repo):

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            mock_analysis.return_value = {
                "jobStatus": "completed",
                "objectType": "facade",
                "surfaceCondition": "good",
                "recommendedScope": "local_repair",
                "estimatedAreaSqm": 10.0,
                "areaConfidence": 0.9,
                "finalAreaSource": "ai",
                "modelName": "mock",
                "modelVersion": "0.1",
            }
            mock_repo.complete_job_with_result = AsyncMock(return_value=(job, MagicMock()))

            service = AnalysisService(
                repository=AsyncMock(spec=AnalysisRepository),
                photo_repository=AsyncMock(spec=PhotoRepository),
                provider_key="mock",
            )

            await service.execute_job("job_1", "prj_A", organization_id="org_A")

        mock_repo.get_project_in_org.assert_called_once_with("prj_A", "org_A")


# ─────────────────────────────────────────────────────────────────────────────
# 3. retry_job — respects organization_id
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryJobOrgScope:

    def test_retry_job_signature_has_organization_id(self):
        from app.services.analysis_service import AnalysisService
        sig = inspect.signature(AnalysisService.retry_job)
        assert "organization_id" in sig.parameters

    def test_retry_job_uses_org_scoped_fetch(self):
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.retry_job)
        assert "get_project_in_org" in src
        assert "organization_id is not None" in src

    @pytest.mark.asyncio
    async def test_retry_job_raises_403_when_project_not_in_org(self):
        """retry_job raises HTTPException(403) if project is not in the given organization."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        original_job = _make_job("job_old", "prj_A")
        original_job.status = "failed"  # Must be terminal to pass the state guard
        session = AsyncMock()

        mock_outer_repo = AsyncMock(spec=AnalysisRepository)
        mock_outer_repo.get_analysis_job = AsyncMock(return_value=original_job)

        mock_inner_repo = AsyncMock(spec=AnalysisRepository)
        # project not in org_B
        mock_inner_repo.get_project_in_org = AsyncMock(return_value=None)

        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory, \
             patch("app.services.analysis_service.AnalysisRepository", return_value=mock_inner_repo):

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            service = AnalysisService(
                repository=mock_outer_repo,
                photo_repository=AsyncMock(spec=PhotoRepository),
                provider_key="mock",
            )

            with pytest.raises(HTTPException) as exc_info:
                await service.retry_job("job_old", organization_id="org_B")

        assert exc_info.value.status_code == 403
        mock_inner_repo.get_project_in_org.assert_called_once_with("prj_A", "org_B")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Missing organization_id — explicit fail, not fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkerExplicitFail:

    def test_execute_job_without_org_id_falls_back_to_session_get(self):
        """When organization_id is None (superadmin), session.get is used — no silent org fallback."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        # Must not default to any hardcoded org
        assert "org_1" not in src
        # Must use session.get in the else branch (for superadmin / internal)
        assert "session.get(Project, project_id)" in src

    def test_mismatch_produces_explicit_failed_status(self):
        """Job status is set to 'failed' explicitly on mismatch — no silent skip."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        # After mismatch detection, status must be failed
        assert '"failed"' in src
        assert "job_project_mismatch" in src

    def test_analysis_repository_get_project_in_org_requires_both_args(self):
        """get_project_in_org must require both project_id and organization_id — no defaults."""
        from app.repositories.analysis_repository import AnalysisRepository
        sig = inspect.signature(AnalysisRepository.get_project_in_org)
        for name in ("project_id", "organization_id"):
            param = sig.parameters[name]
            assert param.default is inspect.Parameter.empty, \
                f"{name} has a default value — should be required"

    def test_routes_pass_org_id_to_execute_job(self):
        """Both routes pass org_id explicitly to the job queue enqueue call (R-19)."""
        from app.api.routes.analysis_jobs import create_analysis_job, retry_analysis_job
        src_create = inspect.getsource(create_analysis_job)
        # R-19: org_id forwarded to enqueue_analysis_job, not BackgroundTasks
        assert "enqueue_analysis_job" in src_create
        assert "organization_id=org_id" in src_create

        src_retry = inspect.getsource(retry_analysis_job)
        assert "enqueue_analysis_job" in src_retry
        assert "organization_id=org_id" in src_retry

    def test_routes_pass_org_id_to_retry_job(self):
        """retry_analysis_job passes org_id to retry_job."""
        from app.api.routes.analysis_jobs import retry_analysis_job
        src = inspect.getsource(retry_analysis_job)
        assert "retry_job(" in src
        assert "organization_id=org_id" in src


# ─────────────────────────────────────────────────────────────────────────────
# 5. organization_id=None — superadmin bypass, not a guard
# ─────────────────────────────────────────────────────────────────────────────

class TestSuperadminBypass:

    def test_execute_job_org_id_none_uses_session_get_path(self):
        """When organization_id=None (superadmin), execute_job uses session.get — no org filter."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        # Superadmin path must exist and be reachable
        assert "session.get(Project, project_id)" in src
        assert "if organization_id is not None:" in src
        # 400 guard must not exist for None case
        assert "status_code=400" not in src

    def test_retry_job_org_id_none_uses_session_get_path(self):
        """When organization_id=None (superadmin), retry_job uses session.get — no org filter."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.retry_job)
        assert "session.get(Project, original.project_id)" in src
        assert "if organization_id is not None:" in src
        # 400 guard must not exist for None case
        assert "status_code=400" not in src

    def test_execute_job_logs_superadmin_bypass(self):
        """execute_job logs when organization_id=None to keep bypass observable."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        assert "superadmin_bypass" in src

    def test_retry_job_logs_superadmin_bypass(self):
        """retry_job logs when organization_id=None to keep bypass observable."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.retry_job)
        assert "superadmin_bypass" in src

    @pytest.mark.asyncio
    async def test_execute_job_without_org_id_and_no_flag_raises_403(self):
        """organization_id=None without is_superadmin_context=True raises 403 guard."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        job = _make_job("job_1", "prj_A")
        service = AnalysisService(
            repository=AsyncMock(spec=AnalysisRepository),
            photo_repository=AsyncMock(spec=PhotoRepository),
            provider_key="mock",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.execute_job("job_1", "prj_A", organization_id=None)
            # is_superadmin_context defaults to False → 403 guard fires immediately

        assert exc_info.value.status_code == 403
        assert "organization_id is required" in exc_info.value.detail
        # Job status must be unmodified (guard fires before any DB operation)
        assert job.status == "queued"

    @pytest.mark.asyncio
    async def test_execute_job_with_superadmin_context_proceeds_to_session_get(self):
        """organization_id=None + is_superadmin_context=True uses session.get path."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        job = _make_job("job_1", "prj_A")
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)  # project not found → 403 project

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)

        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            with patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo), \
                 patch("app.services.analysis_service.PhotoRepository"):

                service = AnalysisService(
                    repository=AsyncMock(spec=AnalysisRepository),
                    photo_repository=AsyncMock(spec=PhotoRepository),
                    provider_key="mock",
                )
                with pytest.raises(HTTPException) as exc_info:
                    await service.execute_job(
                        "job_1", "prj_A", organization_id=None, is_superadmin_context=True
                    )

        # Proceeds past guard → project not found → 403 (not the guard 403)
        assert exc_info.value.status_code == 403
        assert "organization_id is required" not in exc_info.value.detail
        assert job.status == "failed"

    @pytest.mark.asyncio
    async def test_retry_job_without_org_id_and_no_flag_raises_403(self):
        """organization_id=None without is_superadmin_context=True raises 403 guard."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        service = AnalysisService(
            repository=mock_repo,
            photo_repository=AsyncMock(spec=PhotoRepository),
            provider_key="mock",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_nonexistent", organization_id=None)

        assert exc_info.value.status_code == 403
        assert "organization_id is required" in exc_info.value.detail
        mock_repo.get_analysis_job.assert_not_called()  # guard fires before DB lookup

    @pytest.mark.asyncio
    async def test_retry_job_with_superadmin_context_proceeds_to_job_lookup(self):
        """organization_id=None + is_superadmin_context=True proceeds to job lookup."""
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=None)  # job not found → 404

        service = AnalysisService(
            repository=mock_repo,
            photo_repository=AsyncMock(spec=PhotoRepository),
            provider_key="mock",
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_nonexistent", organization_id=None, is_superadmin_context=True)

        assert exc_info.value.status_code == 404  # job not found (guard passed)
        mock_repo.get_analysis_job.assert_called_once_with("job_nonexistent")


# ─────────────────────────────────────────────────────────────────────────────
# 6. retry_job — terminal state and max-retry guards
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryJobGuards:
    """retry_job must reject non-terminal states and enforce the retry ceiling."""

    def _make_service(self, job):
        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        return AnalysisService(
            repository=mock_repo,
            photo_repository=AsyncMock(spec=PhotoRepository),
            provider_key="mock",
        )

    @pytest.mark.asyncio
    async def test_retry_queued_job_raises_409(self):
        """Cannot retry a job that is still queued (active — would create two active jobs)."""
        job = _make_job("job_1", "prj_A")
        job.status = "queued"
        job.retry_count = 0

        service = self._make_service(job)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_1", organization_id="org_A")

        assert exc_info.value.status_code == 409
        assert "queued" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_retry_running_job_raises_409(self):
        """Cannot retry a job that is currently running (would race with the active worker)."""
        job = _make_job("job_1", "prj_A")
        job.status = "running"
        job.retry_count = 0

        service = self._make_service(job)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_1", organization_id="org_A")

        assert exc_info.value.status_code == 409
        assert "running" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_retry_completed_job_raises_409(self):
        """Cannot retry a completed job (use a fresh job creation instead)."""
        job = _make_job("job_1", "prj_A")
        job.status = "completed"
        job.retry_count = 0

        service = self._make_service(job)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_1", organization_id="org_A")

        assert exc_info.value.status_code == 409
        assert "completed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_retry_failed_job_passes_state_guard(self):
        """A failed job passes the state guard (proceeds to org check, not 409)."""
        job = _make_job("job_1", "prj_A")
        job.status = "failed"
        job.retry_count = 0

        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_inner_repo = AsyncMock(spec=AnalysisRepository)
        mock_inner_repo.get_project_in_org = AsyncMock(return_value=None)  # → 403 (not 409)

        session = AsyncMock()
        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory, \
             patch("app.services.analysis_service.AnalysisRepository", return_value=mock_inner_repo):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            service = AnalysisService(
                repository=mock_repo,
                photo_repository=AsyncMock(spec=PhotoRepository),
                provider_key="mock",
            )
            with pytest.raises(HTTPException) as exc_info:
                await service.retry_job("job_1", organization_id="org_A")

        # Reached org check (403), not state guard (409)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_canceled_job_passes_state_guard(self):
        """A canceled job passes the state guard (proceeds to org check, not 409)."""
        job = _make_job("job_1", "prj_A")
        job.status = "canceled"
        job.retry_count = 0

        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_inner_repo = AsyncMock(spec=AnalysisRepository)
        mock_inner_repo.get_project_in_org = AsyncMock(return_value=None)  # → 403

        session = AsyncMock()
        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory, \
             patch("app.services.analysis_service.AnalysisRepository", return_value=mock_inner_repo):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            service = AnalysisService(
                repository=mock_repo,
                photo_repository=AsyncMock(spec=PhotoRepository),
                provider_key="mock",
            )
            with pytest.raises(HTTPException) as exc_info:
                await service.retry_job("job_1", organization_id="org_A")

        # Reached org check (403), not state guard (409)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_retry_max_count_exceeded_raises_409(self):
        """Retry is rejected when retry_count has reached _MAX_JOB_RETRY_COUNT."""
        job = _make_job("job_1", "prj_A")
        job.status = "failed"
        job.retry_count = _MAX_JOB_RETRY_COUNT  # At the ceiling

        service = self._make_service(job)
        with pytest.raises(HTTPException) as exc_info:
            await service.retry_job("job_1", organization_id="org_A")

        assert exc_info.value.status_code == 409
        assert str(_MAX_JOB_RETRY_COUNT) in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_retry_count_below_max_passes_count_guard(self):
        """Retry is not rejected when retry_count is below _MAX_JOB_RETRY_COUNT."""
        job = _make_job("job_1", "prj_A")
        job.status = "failed"
        job.retry_count = _MAX_JOB_RETRY_COUNT - 1  # One below ceiling

        from app.services.analysis_service import AnalysisService
        from app.repositories.analysis_repository import AnalysisRepository
        from app.repositories.photo_repository import PhotoRepository

        mock_repo = AsyncMock(spec=AnalysisRepository)
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_inner_repo = AsyncMock(spec=AnalysisRepository)
        mock_inner_repo.get_project_in_org = AsyncMock(return_value=None)  # → 403 (not 409)

        session = AsyncMock()
        with patch("app.services.analysis_service.AsyncSessionFactory") as mock_factory, \
             patch("app.services.analysis_service.AnalysisRepository", return_value=mock_inner_repo):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = mock_ctx

            service = AnalysisService(
                repository=mock_repo,
                photo_repository=AsyncMock(spec=PhotoRepository),
                provider_key="mock",
            )
            with pytest.raises(HTTPException) as exc_info:
                await service.retry_job("job_1", organization_id="org_A")

        # Reached org check (403), not count guard (409)
        assert exc_info.value.status_code == 403
