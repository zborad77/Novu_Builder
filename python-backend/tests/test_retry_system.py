from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.services.analysis_service import AnalysisService
from app.worker.queue import LeasedAnalysisJob


def _job(*, status: str = "queued", attempt_count: int = 0):
    job = MagicMock()
    job.id = "job-1"
    job.project_id = "proj-1"
    job.status = status
    job.retry_count = 0
    job.attempt_count = attempt_count
    job.started_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
    job.finished_at = None
    job.error_message = None
    job.error_traceback = None
    job.input_payload = None
    job.output_summary = None
    return job


def _project():
    project = MagicMock()
    project.id = "proj-1"
    project.organization_id = "org-1"
    project.created_by_user_id = "usr-1"
    project.title = "Test"
    project.description = None
    project.address_label = None
    project.property_type = "facade"
    project.repair_scope = "local_repair"
    return project


class TestAnalysisRetryDecisions:
    @pytest.mark.asyncio
    async def test_execute_job_schedules_retry_before_max_attempts(self):
        queued_job = _job(status="queued", attempt_count=0)
        running_job = _job(status="running", attempt_count=1)
        project = _project()

        phase1_repo = AsyncMock()
        phase1_repo.get_analysis_job = AsyncMock(return_value=queued_job)
        phase1_repo.get_project_in_org = AsyncMock(return_value=project)

        async def _mark_job_running(job, **_kwargs):
            job.status = "running"
            job.attempt_count = 1
            return job

        phase1_repo.mark_job_running = AsyncMock(side_effect=_mark_job_running)
        phase1_repo.assert_job_lease_owned = AsyncMock(return_value=running_job)

        phase3_repo = AsyncMock()
        phase3_repo.get_analysis_job = AsyncMock(return_value=running_job)
        phase3_repo.assert_job_lease_owned = AsyncMock(return_value=running_job)
        phase3_repo.schedule_job_retry = AsyncMock()
        phase3_repo.mark_job_dead_letter = AsyncMock()

        photo_repo = AsyncMock()
        photo_repo.list_photos_by_project_id = AsyncMock(return_value=[])

        phase1_session = AsyncMock()
        phase1_session.get = AsyncMock(return_value=project)
        phase2_session = AsyncMock()
        phase2_session.get = AsyncMock(return_value=project)

        phase1_ctx = AsyncMock()
        phase1_ctx.__aenter__.return_value = phase1_session
        phase1_ctx.__aexit__.return_value = False
        phase2_ctx = AsyncMock()
        phase2_ctx.__aenter__.return_value = phase2_session
        phase2_ctx.__aexit__.return_value = False

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        settings = SimpleNamespace(
            analysis_job_max_attempts=3,
            analysis_retry_backoff_base_seconds=30,
            analysis_retry_backoff_max_seconds=300,
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory", side_effect=[phase1_ctx, phase2_ctx]),
            patch("app.services.analysis_service.AnalysisRepository", side_effect=[phase1_repo, phase3_repo]),
            patch("app.services.analysis_service.PhotoRepository", return_value=photo_repo),
            patch("app.services.analysis_service.run_project_analysis", side_effect=RuntimeError("provider down")),
            patch("app.services.analysis_service.get_settings", return_value=settings),
        ):
            result = await service.execute_job(
                "job-1",
                "proj-1",
                "org-1",
                lease_token="lease-1",
                worker_id="worker-1",
            )

        assert result.disposition == "retry_scheduled"
        assert result.retry_at is not None
        phase3_repo.schedule_job_retry.assert_awaited_once()
        phase3_repo.mark_job_dead_letter.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_job_dead_letters_when_attempt_budget_is_exhausted(self):
        queued_job = _job(status="queued", attempt_count=0)
        running_job = _job(status="running", attempt_count=3)
        project = _project()

        phase1_repo = AsyncMock()
        phase1_repo.get_analysis_job = AsyncMock(return_value=queued_job)
        phase1_repo.get_project_in_org = AsyncMock(return_value=project)

        async def _mark_job_running(job, **_kwargs):
            job.status = "running"
            job.attempt_count = 3
            return job

        phase1_repo.mark_job_running = AsyncMock(side_effect=_mark_job_running)
        phase1_repo.assert_job_lease_owned = AsyncMock(return_value=running_job)

        phase3_repo = AsyncMock()
        phase3_repo.get_analysis_job = AsyncMock(return_value=running_job)
        phase3_repo.assert_job_lease_owned = AsyncMock(return_value=running_job)
        phase3_repo.schedule_job_retry = AsyncMock()
        phase3_repo.mark_job_dead_letter = AsyncMock()

        photo_repo = AsyncMock()
        photo_repo.list_photos_by_project_id = AsyncMock(return_value=[])

        phase1_session = AsyncMock()
        phase1_session.get = AsyncMock(return_value=project)
        phase2_session = AsyncMock()
        phase2_session.get = AsyncMock(return_value=project)

        phase1_ctx = AsyncMock()
        phase1_ctx.__aenter__.return_value = phase1_session
        phase1_ctx.__aexit__.return_value = False
        phase2_ctx = AsyncMock()
        phase2_ctx.__aenter__.return_value = phase2_session
        phase2_ctx.__aexit__.return_value = False

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        settings = SimpleNamespace(
            analysis_job_max_attempts=3,
            analysis_retry_backoff_base_seconds=30,
            analysis_retry_backoff_max_seconds=300,
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory", side_effect=[phase1_ctx, phase2_ctx]),
            patch("app.services.analysis_service.AnalysisRepository", side_effect=[phase1_repo, phase3_repo]),
            patch("app.services.analysis_service.PhotoRepository", return_value=photo_repo),
            patch("app.services.analysis_service.run_project_analysis", side_effect=RuntimeError("provider down")),
            patch("app.services.analysis_service.get_settings", return_value=settings),
        ):
            result = await service.execute_job(
                "job-1",
                "proj-1",
                "org-1",
                lease_token="lease-1",
                worker_id="worker-1",
            )

        assert result.disposition == "dead_lettered"
        phase3_repo.mark_job_dead_letter.assert_awaited_once()
        phase3_repo.schedule_job_retry.assert_not_called()


class TestDeadLetterReprocess:
    @pytest.mark.asyncio
    async def test_reprocess_dead_letter_job_requeues_dlq_payload(self):
        job = _job(status="dead_letter", attempt_count=3)
        job.project_id = "proj-1"
        job.error_message = "provider failed"
        project = _project()

        outer_repo = AsyncMock()
        outer_repo.get_analysis_job = AsyncMock(return_value=job)

        inner_repo = AsyncMock()
        inner_repo.get_project_in_org = AsyncMock(return_value=project)
        inner_repo.get_analysis_job = AsyncMock(return_value=job)
        inner_repo.count_active_jobs_for_organization = AsyncMock(return_value=0)

        async def _requeue_dead_letter_job(job_obj):
            job_obj.status = "queued"
            job_obj.attempt_count = 0
            return job_obj

        inner_repo.requeue_dead_letter_job = AsyncMock(side_effect=_requeue_dead_letter_job)

        session = AsyncMock()
        session.get = AsyncMock(return_value=project)
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False

        service = AnalysisService(
            repository=outer_repo,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        settings = SimpleNamespace(
            analysis_queue_max_depth=1000,
            analysis_jobs_per_tenant_limit=10,
        )

        with (
            patch("app.services.analysis_service.AsyncSessionFactory", return_value=session_ctx),
            patch("app.services.analysis_service.AnalysisRepository", return_value=inner_repo),
            patch("app.services.analysis_service.get_settings", return_value=settings),
            patch("app.services.analysis_service.requeue_dlq_job", new=AsyncMock(return_value={"job_id": "job-1"})) as requeue_dlq,
        ):
            result = await service.reprocess_dead_letter_job(
                "job-1",
                organization_id=None,
                is_superadmin_context=True,
                job_queue=AsyncMock(),
            )

        assert result.status == "queued"
        assert result.attempt_count == 0
        inner_repo.requeue_dead_letter_job.assert_awaited_once()
        requeue_dlq.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_admin_reprocess_route_returns_429_when_queue_is_full(self):
        from app.api.routes.admin import admin_reprocess_dead_letter_job
        from app.worker.queue import AnalysisJobQueueCapacityExceededError

        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
        current_user = MagicMock(id="admin-1")
        analysis_service = MagicMock(
            reprocess_dead_letter_job=AsyncMock(
                side_effect=AnalysisJobQueueCapacityExceededError(
                    queued=1000,
                    processing=0,
                    max_depth=1000,
                )
            )
        )
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await admin_reprocess_dead_letter_job(
                request=request,
                job_id="job-1",
                current_user=current_user,
                analysis_service=analysis_service,
                session=session,
                job_queue=AsyncMock(),
            )

        assert exc_info.value.status_code == 429


class TestWorkerRetryFinalization:
    @pytest.mark.asyncio
    async def test_run_job_task_schedules_retry_without_ack(self):
        from app.worker import runner

        lease = LeasedAnalysisJob(
            token="lease-1",
            payload={
                "job_id": "job-1",
                "project_id": "proj-1",
                "organization_id": "org-1",
                "is_superadmin_context": False,
            },
            raw_payload='{"job_id":"job-1","project_id":"proj-1","organization_id":"org-1","is_superadmin_context":false}',
            worker_id="worker-1",
            leased_at_ms=1_700_000_000_000,
            lease_timeout_ms=600_000,
            expires_at_ms=1_700_000_600_000,
        )

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://localhost:6379/0",
            worker_instance_id="worker-1",
            heartbeat_key="worker:heartbeat:worker-1",
            job_executor=MagicMock(
                execute_lease=AsyncMock(
                    return_value=SimpleNamespace(
                        disposition="retry_scheduled",
                        retry_at=datetime.now(UTC) + timedelta(seconds=30),
                        attempt_count=1,
                        failure_reason="provider down",
                    )
                )
            ),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=AsyncMock(),
            inflight_tasks=set(),
        )

        runtime.concurrency_limiter.release = MagicMock()

        with (
            patch("app.worker.runner.schedule_analysis_job_retry", new=AsyncMock(return_value=True)) as schedule_retry,
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock()) as ack_job,
        ):
            await runner._run_job_task(runtime, lease)

        schedule_retry.assert_awaited_once()
        ack_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_job_task_moves_dead_letter_to_dlq_without_ack(self):
        from app.worker import runner

        lease = LeasedAnalysisJob(
            token="lease-1",
            payload={
                "job_id": "job-1",
                "project_id": "proj-1",
                "organization_id": "org-1",
                "is_superadmin_context": False,
            },
            raw_payload='{"job_id":"job-1","project_id":"proj-1","organization_id":"org-1","is_superadmin_context":false}',
            worker_id="worker-1",
            leased_at_ms=1_700_000_000_000,
            lease_timeout_ms=600_000,
            expires_at_ms=1_700_000_600_000,
        )

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://localhost:6379/0",
            worker_instance_id="worker-1",
            heartbeat_key="worker:heartbeat:worker-1",
            job_executor=MagicMock(
                execute_lease=AsyncMock(
                    return_value=SimpleNamespace(
                        disposition="dead_lettered",
                        retry_at=None,
                        attempt_count=3,
                        failure_reason="provider down",
                    )
                )
            ),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=AsyncMock(),
            inflight_tasks=set(),
        )

        runtime.concurrency_limiter.release = MagicMock()

        with (
            patch("app.worker.runner.move_analysis_job_to_dlq", new=AsyncMock(return_value=True)) as move_dlq,
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock()) as ack_job,
        ):
            await runner._run_job_task(runtime, lease)

        move_dlq.assert_awaited_once()
        ack_job.assert_not_awaited()
