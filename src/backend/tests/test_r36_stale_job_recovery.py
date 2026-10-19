import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLeaseRecoveryContracts:
    @staticmethod
    def _lease(*, job_id: str, token: str = "lease-1", worker_id: str = "worker-a"):
        lease = MagicMock()
        lease.job_id = job_id
        lease.token = token
        lease.worker_id = worker_id
        lease.leased_at_ms = int(datetime(2026, 3, 30, 12, 0, tzinfo=UTC).timestamp() * 1000)
        lease.lease_timeout_seconds = 600
        return lease

    def test_startup_no_longer_marks_running_jobs_failed(self):
        from app import main

        source = inspect.getsource(main.lifespan)
        assert 'AnalysisJob.status == "running"' not in source
        assert "startup.stale_jobs_recovered" not in source

    def test_worker_runner_uses_lease_reaper(self):
        from app.worker import runner

        source = inspect.getsource(runner._run_one_iteration)
        assert "_run_lease_reaper_if_due" in source

    @pytest.mark.asyncio
    async def test_reconcile_expired_lease_resets_running_job_to_queued(self):
        from app.services.analysis_service import AnalysisService

        job = MagicMock()
        job.id = "job-1"
        job.status = "running"
        job.lease_token = "lease-1"
        job.worker_id = "worker-a"
        job.leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        job.heartbeat_at = datetime(2026, 3, 30, 11, 40, tzinfo=UTC)

        repo = AsyncMock()
        repo.get_analysis_job = AsyncMock(return_value=job)
        repo.reset_job_to_queued = AsyncMock(return_value=job)

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory", return_value=session),
            patch("app.services.analysis_service.AnalysisRepository", return_value=repo),
        ):
            disposition = await service.reconcile_expired_lease(self._lease(job_id="job-1"))

        assert disposition == "requeue"
        repo.reset_job_to_queued.assert_awaited_once_with(job)

    @pytest.mark.asyncio
    async def test_reconcile_expired_lease_drops_completed_job(self):
        from app.services.analysis_service import AnalysisService

        job = MagicMock()
        job.id = "job-2"
        job.status = "completed"
        job.lease_token = "lease-1"
        job.worker_id = "worker-a"
        job.leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        job.heartbeat_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

        repo = AsyncMock()
        repo.get_analysis_job = AsyncMock(return_value=job)

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory", return_value=session),
            patch("app.services.analysis_service.AnalysisRepository", return_value=repo),
        ):
            disposition = await service.reconcile_expired_lease(self._lease(job_id="job-2"))

        assert disposition == "drop"

    @pytest.mark.asyncio
    async def test_reconcile_expired_lease_drops_job_when_db_lease_was_renewed(self):
        from app.services.analysis_service import AnalysisService

        job = MagicMock()
        job.id = "job-3"
        job.status = "running"
        job.lease_token = "lease-1"
        job.worker_id = "worker-a"
        job.leased_at = datetime(2026, 3, 30, 12, 5, tzinfo=UTC)
        job.heartbeat_at = datetime(2026, 3, 30, 12, 5, tzinfo=UTC)

        repo = AsyncMock()
        repo.get_analysis_job = AsyncMock(return_value=job)
        repo.reset_job_to_queued = AsyncMock()

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory", return_value=session),
            patch("app.services.analysis_service.AnalysisRepository", return_value=repo),
        ):
            disposition = await service.reconcile_expired_lease(self._lease(job_id="job-3"))

        assert disposition == "drop"
        repo.reset_job_to_queued.assert_not_awaited()
