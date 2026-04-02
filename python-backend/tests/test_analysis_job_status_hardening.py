from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.repositories.analysis_repository import (
    ANALYSIS_JOB_STATUS_COMPLETED,
    ANALYSIS_JOB_STATUS_DEAD_LETTER,
    ANALYSIS_JOB_STATUS_FAILED,
    ANALYSIS_JOB_STATUS_QUEUED,
    ANALYSIS_JOB_STATUS_RUNNING,
    AnalysisJobLeaseOwnershipError,
    InvalidAnalysisJobStatusError,
    InvalidAnalysisResultPayloadError,
    InvalidAnalysisJobStatusTransition,
    AnalysisRepository,
)
from app.services.analysis_service import AnalysisService
from app.worker.queue import AnalysisJobTransportSnapshot


def _make_job(status: str = "queued") -> MagicMock:
    job = MagicMock()
    job.id = "job_1"
    job.project_id = "proj_1"
    job.status = status
    job.retry_count = 0
    job.lease_token = None
    job.worker_id = None
    job.leased_at = None
    job.heartbeat_at = None
    job.started_at = None
    job.finished_at = None
    job.error_message = None
    job.error_traceback = None
    return job


def _make_project() -> MagicMock:
    project = MagicMock()
    project.id = "proj_1"
    project.created_by_user_id = "usr_1"
    project.title = "Test project"
    project.description = None
    project.address_label = None
    project.status = "draft"
    project.property_type = "facade"
    project.repair_scope = "local_repair"
    project.updated_at = None
    return project


class TestAnalysisRepositoryStatusGuards:
    @pytest.mark.asyncio
    async def test_fail_job_sets_terminal_failure_fields(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        repo = AnalysisRepository(session)
        job = _make_job()

        before = datetime.now(UTC)
        await repo.fail_job(job, message="payload invalid")

        assert job.status == "failed"
        assert job.error_message == "payload invalid"
        assert job.finished_at is not None
        assert job.finished_at >= before
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(job)

    @pytest.mark.asyncio
    async def test_update_status_blocks_transition_from_completed_to_running(self):
        session = AsyncMock()
        repo = AnalysisRepository(session)
        job = _make_job(status=ANALYSIS_JOB_STATUS_COMPLETED)

        with pytest.raises(InvalidAnalysisJobStatusTransition):
            await repo.update_analysis_job_status(job, ANALYSIS_JOB_STATUS_RUNNING)

        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_job_with_result_rejects_non_completed_provider_status(self):
        session = AsyncMock()
        repo = AnalysisRepository(session)
        job = _make_job(status=ANALYSIS_JOB_STATUS_RUNNING)
        job.started_at = datetime.now(UTC)
        project = _make_project()

        with pytest.raises(InvalidAnalysisJobStatusError):
            await repo.complete_job_with_result(job, project, {"jobStatus": "failed"})

        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_job_with_result_rejects_invalid_numeric_without_terminal_transition(self):
        session = AsyncMock()
        repo = AnalysisRepository(session)
        job = _make_job(status=ANALYSIS_JOB_STATUS_RUNNING)
        job.started_at = datetime.now(UTC)
        project = _make_project()

        with pytest.raises(InvalidAnalysisResultPayloadError):
            await repo.complete_job_with_result(
                job,
                project,
                {
                    "jobStatus": "completed",
                    "estimatedAreaSqm": "not-a-number",
                },
            )

        assert job.status == ANALYSIS_JOB_STATUS_RUNNING
        assert job.finished_at is None
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_job_with_result_returns_existing_result_for_already_completed_job(self):
        session = AsyncMock()
        session.refresh = AsyncMock()
        repo = AnalysisRepository(session)
        job = _make_job(status=ANALYSIS_JOB_STATUS_COMPLETED)
        existing_result = MagicMock()

        with patch.object(repo, "get_analysis_result_by_job_id", new=AsyncMock(return_value=existing_result)):
            returned_job, returned_result = await repo.complete_job_with_result(
                job,
                _make_project(),
                {"jobStatus": "completed", "estimatedAreaSqm": 1.0},
            )

        assert returned_job is job
        assert returned_result is existing_result
        session.commit.assert_not_called()
        session.refresh.assert_any_await(job)
        session.refresh.assert_any_await(existing_result)

    @pytest.mark.asyncio
    async def test_mark_job_running_rejects_duplicate_claim_after_race(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "status", ANALYSIS_JOB_STATUS_RUNNING))
        session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        repo = AnalysisRepository(session)
        job = _make_job(status=ANALYSIS_JOB_STATUS_QUEUED)

        with pytest.raises(InvalidAnalysisJobStatusTransition):
            await repo.mark_job_running(job)

        session.commit.assert_not_called()
        session.refresh.assert_awaited_once_with(job)
        assert job.status == ANALYSIS_JOB_STATUS_RUNNING


class TestAnalysisServiceFailureGuards:
    @pytest.mark.asyncio
    async def test_execute_job_missing_org_marks_job_failed_before_raising(self):
        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        job = _make_job()
        session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=job)

        with (
            patch.object(service, "fail_job_before_processing", new=AsyncMock(return_value=True)) as fail_job,
            patch("app.services.analysis_service.WorkerAsyncSessionFactory") as factory,
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            factory.return_value = ctx

            with pytest.raises(HTTPException) as exc_info:
                await service.execute_job(
                    "job_1",
                    "proj_1",
                    organization_id=None,
                    is_superadmin_context=False,
                )

        assert exc_info.value.status_code == 403
        fail_job.assert_awaited_once()
        assert "organization_id is required" in fail_job.await_args.kwargs["message"]

    @pytest.mark.asyncio
    async def test_fail_job_before_processing_returns_false_for_terminal_job(self):
        job = _make_job(status="completed")
        session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_repo.fail_job = AsyncMock(side_effect=InvalidAnalysisJobStatusTransition("done"))

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory") as factory,
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            factory.return_value = ctx

            result = await service.fail_job_before_processing("job_1", message="bad payload")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_job_reconciles_stale_running_job_to_queued(self):
        job = _make_job(status=ANALYSIS_JOB_STATUS_RUNNING)
        job.worker_id = "worker-a"
        job.lease_token = "lease-a"
        job.heartbeat_at = datetime.now(UTC).replace(year=2025)
        repository = AsyncMock()
        repository.get_analysis_job_in_org = AsyncMock(return_value=job)
        repository.get_project_organization_id = AsyncMock(return_value="org-1")
        repository.reset_job_to_queued = AsyncMock(side_effect=lambda current_job: setattr(current_job, "status", ANALYSIS_JOB_STATUS_QUEUED) or current_job)

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )
        service._settings.worker_job_lease_timeout_seconds = 600

        result = await service.get_job(
            "job_1",
            organization_id="org-1",
            job_queue=None,
        )

        assert result is not None
        assert result["status"] == ANALYSIS_JOB_STATUS_QUEUED
        repository.reset_job_to_queued.assert_awaited_once_with(job)

    @pytest.mark.asyncio
    async def test_list_jobs_requeues_missing_queued_transport(self):
        job = _make_job(status=ANALYSIS_JOB_STATUS_QUEUED)
        repository = AsyncMock()
        repository.list_analysis_jobs_by_project_id = AsyncMock(return_value=[job])
        repository.get_project_organization_id = AsyncMock(return_value="org-1")

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )
        service._settings.analysis_queue_max_depth = 100

        snapshot = AnalysisJobTransportSnapshot(
            queued=(),
            processing=(),
            scheduled_retry=(),
            dlq_job_ids=frozenset(),
        )
        job_queue = AsyncMock()
        job_queue.eval = AsyncMock(return_value=[1, 1, 0])

        with patch("app.services.analysis_service.inspect_analysis_job_transport", new=AsyncMock(return_value=snapshot)):
            results = await service.list_jobs("proj_1", job_queue=job_queue)

        assert results[0]["status"] == ANALYSIS_JOB_STATUS_QUEUED
        job_queue.eval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_job_invalid_analysis_payload_schedules_retry(self):
        job = _make_job()
        project = _make_project()
        session = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_repo.get_project_in_org = AsyncMock(return_value=project)

        async def _mark_running(current_job, **_kwargs):
            current_job.status = ANALYSIS_JOB_STATUS_RUNNING
            current_job.started_at = datetime.now(UTC)
            return current_job

        async def _mark_dead_letter(current_job, *, message, error_traceback=None):
            current_job.status = ANALYSIS_JOB_STATUS_DEAD_LETTER
            current_job.error_message = message
            current_job.error_traceback = error_traceback
            current_job.finished_at = datetime.now(UTC)
            return current_job

        mock_repo.mark_job_running = AsyncMock(side_effect=_mark_running)
        mock_repo.complete_job_with_result = AsyncMock(
            side_effect=InvalidAnalysisResultPayloadError(
                "estimatedAreaSqm must be numeric when provided."
            )
        )
        mock_repo.mark_job_dead_letter = AsyncMock(side_effect=_mark_dead_letter)

        mock_photo_repo = AsyncMock()
        mock_photo_repo.list_photos_by_project_id = AsyncMock(return_value=[])

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory") as factory,
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
            patch("app.services.analysis_service.PhotoRepository", return_value=mock_photo_repo),
            patch(
                "app.services.analysis_service.run_project_analysis",
                new=AsyncMock(return_value={"jobStatus": "completed", "estimatedAreaSqm": "bad"}),
            ),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            factory.return_value = ctx

            await service.execute_job("job_1", "proj_1", organization_id="org_1")

        mock_repo.mark_job_dead_letter.assert_awaited_once()
        assert job.status == ANALYSIS_JOB_STATUS_DEAD_LETTER
        assert job.error_message.startswith("Invalid analysis payload:")

    @pytest.mark.asyncio
    async def test_execute_job_skips_duplicate_claim_without_running_provider(self):
        job = _make_job()
        project = _make_project()
        session = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=job)
        mock_repo.get_project_in_org = AsyncMock(return_value=project)
        mock_repo.mark_job_running = AsyncMock(
            side_effect=InvalidAnalysisJobStatusTransition("already running elsewhere")
        )
        mock_photo_repo = AsyncMock()

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory") as factory,
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
            patch("app.services.analysis_service.PhotoRepository", return_value=mock_photo_repo),
            patch("app.services.analysis_service.run_project_analysis", new=AsyncMock()) as run_analysis,
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            factory.return_value = ctx

            await service.execute_job("job_1", "proj_1", organization_id="org_1")

        run_analysis.assert_not_awaited()
        mock_repo.complete_job_with_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_job_aborts_when_db_lease_no_longer_matches(self):
        job = _make_job(status=ANALYSIS_JOB_STATUS_QUEUED)
        project = _make_project()
        session = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(side_effect=[job, job, job])
        mock_repo.get_project_in_org = AsyncMock(return_value=project)

        async def _mark_running(current_job, **_kwargs):
            current_job.status = ANALYSIS_JOB_STATUS_RUNNING
            current_job.started_at = datetime.now(UTC)
            return current_job

        mock_repo.mark_job_running = AsyncMock(side_effect=_mark_running)
        mock_repo.assert_job_lease_owned = AsyncMock(
            side_effect=[job, AnalysisJobLeaseOwnershipError("lost lease")]
        )
        mock_photo_repo = AsyncMock()
        mock_photo_repo.list_photos_by_project_id = AsyncMock(return_value=[])

        service = AnalysisService(
            repository=AsyncMock(),
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.WorkerAsyncSessionFactory") as factory,
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
            patch("app.services.analysis_service.PhotoRepository", return_value=mock_photo_repo),
            patch(
                "app.services.analysis_service.run_project_analysis",
                new=AsyncMock(return_value={"jobStatus": "completed", "estimatedAreaSqm": 1.0}),
            ),
        ):
            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            factory.return_value = ctx

            with pytest.raises(AnalysisJobLeaseOwnershipError):
                await service.execute_job(
                    "job_1",
                    "proj_1",
                    organization_id="org_1",
                    lease_token="lease-1",
                    worker_id="worker-a",
                )

    @pytest.mark.asyncio
    async def test_cancel_analysis_job_is_idempotent_for_failed_job(self):
        failed_job = _make_job(status=ANALYSIS_JOB_STATUS_FAILED)
        repository = AsyncMock()
        repository.get_analysis_job_in_org = AsyncMock(return_value=failed_job)
        repository.update_analysis_job_status = AsyncMock()

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        result = await service.cancel_analysis_job("job_1", organization_id="org_1")

        assert result is not None
        assert result["status"] == ANALYSIS_JOB_STATUS_FAILED
        repository.update_analysis_job_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_manual_selection_by_result_id_enforces_org_scope(self):
        repository = AsyncMock()
        repository.get_analysis_result_in_org = AsyncMock(return_value=None)
        repository.get_analysis_result = AsyncMock()

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        result = await service.update_manual_selection_by_result_id(
            "ana_1",
            {"manualAreaSqm": 12.5},
            organization_id="org_denied",
        )

        assert result is None
        repository.get_analysis_result_in_org.assert_awaited_once_with("ana_1", "org_denied")
        repository.get_analysis_result.assert_not_awaited()
        repository.update_analysis_manual_selection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_manual_selection_by_result_id_updates_scoped_result(self):
        repository = AsyncMock()
        stored = MagicMock()
        stored.id = "ana_1"
        stored.project_id = "proj_1"
        stored.analysis_job_id = "job_1"
        stored.reference_photo_id = "pho_1"
        stored.selected_repair_polygon_json = '[{"x": 1.0, "y": 2.0}]'
        stored.manual_area_sqm = 18.0
        stored.final_area_source = "manual"
        stored.estimated_area_sqm = 10.0
        stored.area_confidence = 0.9
        stored.object_type = "facade"
        stored.surface_condition = "requires_attention"
        stored.recommended_scope = "local_repair"
        stored.mask_polygon_json = "[]"
        stored.materials_suggestion_json = "[]"
        stored.workflow_suggestion_json = "[]"
        stored.estimated_duration_days = None
        stored.labor_hours_total = None
        stored.model_name = "mock"
        stored.model_version = "0.1"
        stored.created_at = None
        repository.get_analysis_result_in_org = AsyncMock(return_value=stored)
        repository.update_analysis_manual_selection = AsyncMock(return_value=stored)

        service = AnalysisService(
            repository=repository,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        result = await service.update_manual_selection_by_result_id(
            "ana_1",
            {"manualAreaSqm": 18.0},
            organization_id="org_1",
        )

        assert result is not None
        assert result.id == "ana_1"
        repository.get_analysis_result_in_org.assert_awaited_once_with("ana_1", "org_1")
        repository.update_analysis_manual_selection.assert_awaited_once_with(stored, {"manualAreaSqm": 18.0})
