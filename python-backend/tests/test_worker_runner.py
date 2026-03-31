import asyncio
import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.queue import InvalidAnalysisJobPayloadError, LeasedAnalysisJob
from app.worker.heavy_queue import LeasedHeavyJob, LostHeavyJobLeaseError


def _lease(
    *,
    job_id: str = "job_abc123",
    project_id: str = "proj-1",
    organization_id: str | None = "org-1",
    is_superadmin_context: bool = False,
    worker_id: str = "worker-a",
    token: str = "lease-1",
) -> LeasedAnalysisJob:
    return LeasedAnalysisJob(
        token=token,
        payload={
            "job_id": job_id,
            "project_id": project_id,
            "organization_id": organization_id,
            "is_superadmin_context": is_superadmin_context,
        },
        raw_payload="{}",
        worker_id=worker_id,
        leased_at_ms=1_700_000_000_000,
        lease_timeout_ms=600_000,
        expires_at_ms=1_700_000_600_000,
    )


def _heavy_lease(
    *,
    job_type: str = "export_generate",
    project_id: str = "proj-1",
    organization_id: str | None = "org-1",
    export_id: str | None = "exp-1",
    photo_id: str | None = None,
    worker_id: str = "worker-a",
    token: str = "heavy-lease-1",
) -> LeasedHeavyJob:
    return LeasedHeavyJob(
        token=token,
        payload={
            "job_type": job_type,
            "project_id": project_id,
            "organization_id": organization_id,
            "export_id": export_id,
            "photo_id": photo_id,
        },
        raw_payload="{}",
        worker_id=worker_id,
        leased_at_ms=1_700_000_000_000,
        lease_timeout_ms=1_800_000,
        expires_at_ms=1_700_001_800_000,
    )


class TestProcessOnePayloadValidation:
    @pytest.mark.asyncio
    async def test_valid_payload_calls_execute_job(self):
        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()
        mock_service.fail_job_before_processing = AsyncMock()

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one

            await _process_one(payload, settings)

        mock_service.execute_job.assert_awaited_once_with(
            "job_abc123",
            "proj-1",
            "org-1",
            is_superadmin_context=False,
            job_queue=None,
        )
        mock_service.fail_job_before_processing.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_project_id_marks_job_failed_without_processing(self):
        payload = {
            "job_id": "job_abc123",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()
        mock_service.fail_job_before_processing = AsyncMock(return_value=True)

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one

            await _process_one(payload, settings)

        mock_service.execute_job.assert_not_called()
        mock_service.fail_job_before_processing.assert_awaited_once()
        assert mock_service.fail_job_before_processing.await_args.kwargs["message"].startswith(
            "Invalid worker payload:"
        )

    @pytest.mark.asyncio
    async def test_missing_org_id_for_non_superadmin_marks_job_failed(self):
        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": None,
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()
        mock_service.fail_job_before_processing = AsyncMock(return_value=True)

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one

            await _process_one(payload, settings)

        mock_service.execute_job.assert_not_called()
        mock_service.fail_job_before_processing.assert_awaited_once()
        assert mock_service.fail_job_before_processing.await_args.args == ("job_abc123",)
        assert "organization_id is required" in mock_service.fail_job_before_processing.await_args.kwargs["message"]

    @pytest.mark.asyncio
    async def test_invalid_superadmin_flag_type_is_rejected(self):
        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": "false",
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()
        mock_service.fail_job_before_processing = AsyncMock(return_value=True)

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one

            await _process_one(payload, settings)

        mock_service.execute_job.assert_not_called()
        mock_service.fail_job_before_processing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_mapping_payload_is_rejected_without_failure_write(self):
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()
        mock_service.fail_job_before_processing = AsyncMock()

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one

            await _process_one([], settings)  # type: ignore[arg-type]

        mock_service.execute_job.assert_not_called()
        mock_service.fail_job_before_processing.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_wraps_unexpected_job_error_without_reclassifying_as_payload_error(self):
        from app.worker.runner import WorkerJobExecutionError, WorkerJobExecutor

        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock(side_effect=RuntimeError("provider blew up"))
        mock_service.fail_job_before_processing = AsyncMock()

        executor = WorkerJobExecutor(settings, service_factory=lambda _settings: mock_service)

        with pytest.raises(WorkerJobExecutionError) as exc_info:
            await executor.execute_payload(payload)

        assert exc_info.value.job_id == "job_abc123"
        assert exc_info.value.project_id == "proj-1"
        assert isinstance(exc_info.value.cause, RuntimeError)
        mock_service.fail_job_before_processing.assert_not_awaited()


class TestWorkerRedisConnectionHardening:
    def test_worker_builder_uses_shared_hardening_with_no_socket_timeout(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"

        with patch("app.worker.runner.build_queue_redis_client_from_settings", return_value=object()) as build_client:
            runner._build_worker_redis(settings, "redis://:secret@localhost:6379/0")

        build_client.assert_called_once_with(
            settings,
            redis_url="redis://:secret@localhost:6379/0",
            socket_timeout=None,
            client_name="novu-worker",
        )

    def test_worker_source_has_no_local_storage_usage(self):
        from app.worker import runner

        source = inspect.getsource(runner)
        assert "local_photo_storage" not in source
        assert "STORAGE_ROOT" not in source
        assert "read_bytes(" not in source
        assert "write_bytes(" not in source
        assert "app.storage.backend" not in source

    @pytest.mark.asyncio
    async def test_worker_startup_fails_fast_when_redis_is_unavailable_in_production(self):
        from app.worker import runner

        settings = MagicMock()
        settings.app_env = "production"

        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=OSError("redis down"))
        redis.aclose = AsyncMock()

        with pytest.raises(RuntimeError, match=r"^Startup validation failed \[redis\]:"):
            await runner._verify_worker_redis_startup(
                redis,
                settings,
                "redis://:secret@localhost:6379/0",
            )

        redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_worker_startup_redis_failure_is_tolerated_in_development(self):
        from app.worker import runner

        settings = MagicMock()
        settings.app_env = "development"

        redis = AsyncMock()
        redis.ping = AsyncMock(side_effect=OSError("redis down"))
        redis.aclose = AsyncMock()

        await runner._verify_worker_redis_startup(
            redis,
            settings,
            "redis://:secret@localhost:6379/0",
        )

        redis.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_rebuilds_redis_client_after_loop_error(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 1
        settings.worker_heavy_concurrency = 0
        settings.worker_heavy_job_lease_timeout_seconds = 1800
        settings.worker_heavy_job_reap_interval_seconds = 30

        first_client = AsyncMock()
        first_client.set = AsyncMock(side_effect=OSError("redis down"))
        first_client.aclose = AsyncMock()

        second_client = AsyncMock()
        second_client.set = AsyncMock(side_effect=asyncio.CancelledError())
        second_client.aclose = AsyncMock()

        with (
            patch("app.worker.runner.get_settings", return_value=settings),
            patch("app.worker.runner._build_worker_redis", side_effect=[first_client, second_client]) as build_client,
            patch("app.worker.runner._verify_worker_redis_startup", new=AsyncMock()) as verify_startup,
            patch("app.worker.runner.asyncio.sleep", new=AsyncMock()) as sleep_mock,
        ):
            await runner.run()

        assert build_client.call_count == 2
        verify_startup.assert_awaited_once_with(first_client, settings, settings.redis_url)
        first_client.aclose.assert_awaited_once()
        second_client.aclose.assert_awaited_once()
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_continues_after_invalid_queue_payload(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 1
        settings.worker_heavy_concurrency = 0
        settings.worker_heavy_job_lease_timeout_seconds = 1800
        settings.worker_heavy_job_reap_interval_seconds = 30

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = _lease()

        with (
            patch("app.worker.runner.get_settings", return_value=settings),
            patch("app.worker.runner._build_worker_redis", return_value=redis),
            patch("app.worker.runner._verify_worker_redis_startup", new=AsyncMock()) as verify_startup,
            patch(
                "app.worker.runner.dequeue_analysis_job",
                side_effect=[
                    InvalidAnalysisJobPayloadError("malformed json"),
                    valid_payload,
                    asyncio.CancelledError(),
                ],
            ),
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock(return_value=True)),
            patch("app.worker.runner.WorkerJobExecutor.execute_lease", new=AsyncMock()) as execute_payload,
        ):
            await runner.run()

        verify_startup.assert_awaited_once_with(redis, settings, settings.redis_url)
        execute_payload.assert_awaited_once()
        redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_keeps_loop_alive_after_job_execution_error(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 1
        settings.worker_heavy_concurrency = 0
        settings.worker_heavy_job_lease_timeout_seconds = 1800
        settings.worker_heavy_job_reap_interval_seconds = 30

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = _lease()
        job_error = runner.WorkerJobExecutionError(
            job_id="job_abc123",
            project_id="proj-1",
            organization_id="org-1",
            cause=RuntimeError("provider blew up"),
        )

        with (
            patch("app.worker.runner.get_settings", return_value=settings),
            patch("app.worker.runner._build_worker_redis", return_value=redis) as build_client,
            patch("app.worker.runner._verify_worker_redis_startup", new=AsyncMock()),
            patch(
                "app.worker.runner.dequeue_analysis_job",
                side_effect=[valid_payload, asyncio.CancelledError()],
            ),
            patch(
                "app.worker.runner.WorkerJobExecutor.execute_lease",
                new=AsyncMock(side_effect=[job_error, asyncio.CancelledError()]),
            ),
            patch("app.worker.runner.asyncio.sleep", new=AsyncMock()) as sleep_mock,
        ):
            await runner.run()

        build_client.assert_called_once_with(settings, settings.redis_url)
        sleep_mock.assert_not_awaited()
        redis.aclose.assert_awaited_once()

    def test_run_uses_shared_builder_instead_of_inline_redis_from_url(self):
        import inspect
        from app.worker import runner

        src = inspect.getsource(runner.run)
        assert "_build_worker_redis(settings, url)" in src

    @pytest.mark.asyncio
    async def test_run_writes_heartbeat_before_entering_main_loop(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 1
        settings.worker_heavy_concurrency = 0
        settings.worker_heavy_job_lease_timeout_seconds = 1800
        settings.worker_heavy_job_reap_interval_seconds = 30

        redis = AsyncMock()
        redis.aclose = AsyncMock()

        with (
            patch("app.worker.runner.get_settings", return_value=settings),
            patch("app.worker.runner._build_worker_redis", return_value=redis),
            patch("app.worker.runner._verify_worker_redis_startup", new=AsyncMock()),
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()) as write_heartbeat,
            patch("app.worker.runner._run_one_iteration", new=AsyncMock(side_effect=asyncio.CancelledError())),
            patch("app.worker.runner.clear_worker_heartbeat", new=AsyncMock()),
        ):
            await runner.run()

        write_heartbeat.assert_awaited_once()


class TestWorkerConcurrencyControl:
    @pytest.mark.asyncio
    async def test_run_one_iteration_spawns_background_jobs_up_to_configured_limit(self):
        from app.worker import runner

        payload_one = _lease(job_id="job_1", token="lease-1")
        payload_two = _lease(job_id="job_2", project_id="proj-2", token="lease-2")
        started = asyncio.Event()
        release = asyncio.Event()
        started_jobs = 0

        async def _execute_payload(payload, **_kwargs):
            nonlocal started_jobs
            started_jobs += 1
            if started_jobs == 2:
                started.set()
            await release.wait()

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock(side_effect=_execute_payload)),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
            worker_concurrency=2,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(2),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
        )

        with (
            patch(
                "app.worker.runner.dequeue_analysis_job",
                new=AsyncMock(side_effect=[payload_one, payload_two]),
            ),
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock(return_value=True)),
        ):
            await runner._run_one_iteration(runtime)
            await runner._run_one_iteration(runtime)
            await asyncio.wait_for(started.wait(), timeout=1)

        assert len(runtime.inflight_tasks) == 2
        assert runtime.concurrency_limiter.locked() is True

        release.set()
        await asyncio.wait_for(asyncio.gather(*list(runtime.inflight_tasks)), timeout=1)
        await runner._drain_finished_tasks(runtime)

        assert len(runtime.inflight_tasks) == 0
        assert runtime.concurrency_limiter.locked() is False

    @pytest.mark.asyncio
    async def test_run_one_iteration_skips_dequeue_when_single_worker_slot_is_busy(self):
        from app.worker import runner

        pending_task = asyncio.create_task(asyncio.sleep(3600))
        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock()),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks={pending_task},
            last_heartbeat=time.monotonic(),
        )
        await runtime.concurrency_limiter.acquire()

        with (
            patch("app.worker.runner._seconds_until_next_heartbeat", return_value=0),
            patch("app.worker.runner.dequeue_analysis_job", new=AsyncMock()) as dequeue,
        ):
            await runner._run_one_iteration(runtime)

        dequeue.assert_not_awaited()
        pending_task.cancel()
        await asyncio.gather(pending_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_run_one_iteration_dequeues_heavy_job_even_when_analysis_slot_is_busy(self):
        from app.worker import runner

        heavy_payload = _heavy_lease(job_type="photo_variant_processing", photo_id="pho_1", export_id=None)
        release = asyncio.Event()

        async def _execute_heavy(_lease):
            await release.wait()

        analysis_pending_task = asyncio.create_task(asyncio.sleep(3600))
        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock()),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock(side_effect=_execute_heavy)),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks={analysis_pending_task},
            worker_heavy_concurrency=1,
            heavy_job_lease_timeout_seconds=1800,
            heavy_lease_reap_interval_seconds=30,
            heavy_concurrency_limiter=asyncio.Semaphore(1),
            last_heartbeat=time.monotonic(),
        )
        await runtime.concurrency_limiter.acquire()

        with (
            patch("app.worker.runner._seconds_until_next_heartbeat", return_value=0),
            patch("app.worker.runner.dequeue_analysis_job", new=AsyncMock()) as dequeue_analysis,
            patch("app.worker.runner.dequeue_heavy_job", new=AsyncMock(return_value=heavy_payload)) as dequeue_heavy,
            patch("app.worker.runner.ack_heavy_job", new=AsyncMock(return_value=True)),
        ):
            await runner._run_one_iteration(runtime)

        dequeue_analysis.assert_not_awaited()
        dequeue_heavy.assert_awaited_once()
        assert len(runtime.inflight_heavy_tasks) == 1

        release.set()
        await asyncio.wait_for(asyncio.gather(*list(runtime.inflight_heavy_tasks)), timeout=1)
        await runner._drain_finished_tasks(runtime)

        analysis_pending_task.cancel()
        await asyncio.gather(analysis_pending_task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_run_cancels_inflight_tasks_on_shutdown_without_leaking(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 2
        settings.worker_heavy_concurrency = 0
        settings.worker_heavy_job_lease_timeout_seconds = 1800
        settings.worker_heavy_job_reap_interval_seconds = 30

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = _lease()
        task_started = asyncio.Event()
        task_cancelled = asyncio.Event()
        dequeue_calls = 0

        async def _execute_payload(_payload, **_kwargs):
            task_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                task_cancelled.set()
                raise

        async def _dequeue_payload(*_args, **_kwargs):
            nonlocal dequeue_calls
            dequeue_calls += 1
            if dequeue_calls == 1:
                return valid_payload
            await asyncio.wait_for(task_started.wait(), timeout=1)
            raise asyncio.CancelledError()

        with (
            patch("app.worker.runner.get_settings", return_value=settings),
            patch("app.worker.runner._build_worker_redis", return_value=redis),
            patch("app.worker.runner._verify_worker_redis_startup", new=AsyncMock()),
            patch(
                "app.worker.runner.dequeue_analysis_job",
                new=AsyncMock(side_effect=_dequeue_payload),
            ),
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock(return_value=True)),
            patch(
                "app.worker.runner.WorkerJobExecutor.execute_lease",
                new=AsyncMock(side_effect=_execute_payload),
            ),
        ):
            await runner.run()

        assert task_started.is_set() is True
        assert task_cancelled.is_set() is True
        redis.aclose.assert_awaited_once()


class TestWorkerExportCleanup:
    @pytest.mark.asyncio
    async def test_run_export_cleanup_if_due_uses_worker_session_factory(self):
        from app.worker import runner

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock()),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
            last_export_cleanup=0.0,
        )

        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        delete_expired_exports = AsyncMock(return_value=2)

        with (
            patch("app.worker.runner.WorkerAsyncSessionFactory", return_value=session_ctx) as session_factory,
            patch("app.worker.runner.ExportService") as export_service_cls,
        ):
            export_service_cls.return_value.delete_expired_exports = delete_expired_exports
            await runner._run_export_cleanup_if_due(
                runtime,
                now_monotonic=runner._EXPORT_CLEANUP_INTERVAL_SECONDS,
            )

        session_factory.assert_called_once_with()
        export_service_cls.assert_called_once()
        delete_expired_exports.assert_awaited_once_with()
        assert runtime.last_export_cleanup == runner._EXPORT_CLEANUP_INTERVAL_SECONDS

    @pytest.mark.asyncio
    async def test_run_photo_cleanup_if_due_uses_worker_session_factory(self):
        from app.worker import runner

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock()),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
            last_photo_cleanup=0.0,
        )

        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        cleanup_pending_deletes = AsyncMock(return_value=2)

        with (
            patch("app.worker.runner.WorkerAsyncSessionFactory", return_value=session_ctx) as session_factory,
            patch("app.worker.runner.PhotoService") as photo_service_cls,
            patch("app.worker.runner.PhotoRepository"),
        ):
            photo_service_cls.return_value.cleanup_pending_deletes = cleanup_pending_deletes
            await runner._run_photo_cleanup_if_due(
                runtime,
                now_monotonic=runner._PHOTO_DELETE_CLEANUP_INTERVAL_SECONDS,
            )

        session_factory.assert_called_once_with()
        photo_service_cls.assert_called_once()
        cleanup_pending_deletes.assert_awaited_once_with()
        assert runtime.last_photo_cleanup == runner._PHOTO_DELETE_CLEANUP_INTERVAL_SECONDS

    @pytest.mark.asyncio
    async def test_run_one_iteration_runs_export_cleanup_before_dequeue(self):
        from app.worker import runner

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_lease=AsyncMock()),
            heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
            worker_concurrency=1,
            job_lease_timeout_seconds=600,
            lease_reap_interval_seconds=30,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
        )

        with (
            patch("app.worker.runner._run_export_cleanup_if_due", new=AsyncMock()) as cleanup,
            patch("app.worker.runner._run_photo_cleanup_if_due", new=AsyncMock()) as photo_cleanup,
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()) as heartbeat,
            patch("app.worker.runner._drain_finished_tasks", new=AsyncMock()) as drain,
            patch("app.worker.runner._acquire_job_slot", new=AsyncMock(return_value=False)) as acquire,
        ):
            await runner._run_one_iteration(runtime)

        cleanup.assert_awaited_once_with(runtime)
        photo_cleanup.assert_awaited_once_with(runtime)
        heartbeat.assert_awaited_once_with(runtime)
        drain.assert_awaited_once_with(runtime)
        acquire.assert_awaited_once_with(runtime)


def _make_runtime(
    *,
    worker_heavy_concurrency: int = 0,
    heavy_job_lease_timeout_seconds: int = 1800,
    heavy_lease_reap_interval_seconds: int = 30,
    last_heavy_lease_reap: float = 0.0,
) -> "runner_module.WorkerRuntime":
    from app.worker import runner as runner_module

    return runner_module.WorkerRuntime(
        settings=MagicMock(),
        redis=AsyncMock(),
        redis_url="redis://localhost:6379/0",
        worker_instance_id="worker-a",
        heartbeat_key="worker:heartbeat:worker-a",
        job_executor=MagicMock(execute_lease=AsyncMock()),
        heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
        worker_concurrency=1,
        job_lease_timeout_seconds=600,
        lease_reap_interval_seconds=30,
        concurrency_limiter=asyncio.Semaphore(1),
        inflight_tasks=set(),
        worker_heavy_concurrency=worker_heavy_concurrency,
        heavy_job_lease_timeout_seconds=heavy_job_lease_timeout_seconds,
        heavy_lease_reap_interval_seconds=heavy_lease_reap_interval_seconds,
        heavy_concurrency_limiter=asyncio.Semaphore(max(1, worker_heavy_concurrency or 1)),
        last_heartbeat=time.monotonic(),
        last_heavy_lease_reap=last_heavy_lease_reap,
    )


class TestHeavyWorkerJobExecutor:
    """Unit tests for HeavyWorkerJobExecutor.execute_lease dispatch."""

    @pytest.mark.asyncio
    async def test_export_generate_calls_export_service(self):
        from app.worker.runner import HeavyWorkerJobExecutor

        lease = _heavy_lease(job_type="export_generate", export_id="exp-1", photo_id=None)

        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False

        process_export = AsyncMock()

        with (
            patch("app.worker.runner.WorkerAsyncSessionFactory", return_value=session_ctx),
            patch("app.worker.runner.ProjectService") as project_service_cls,
            patch("app.worker.runner.ExportService") as export_service_cls,
            patch("app.worker.runner.ExportRepository"),
            patch("app.worker.runner.ProjectRepository"),
            patch("app.worker.runner.ProposalDraftRepository"),
            patch("app.worker.runner.FinalProposalRepository"),
        ):
            case_detail = MagicMock()
            project_service_cls.return_value.get_project_detail = AsyncMock(return_value=case_detail)
            export_service_cls.return_value.process_export_by_id = process_export

            await HeavyWorkerJobExecutor().execute_lease(lease)

        process_export.assert_awaited_once_with("exp-1", case_detail=case_detail)

    @pytest.mark.asyncio
    async def test_photo_variant_processing_calls_photo_service(self):
        from app.worker.runner import HeavyWorkerJobExecutor

        lease = _heavy_lease(job_type="photo_variant_processing", photo_id="pho-1", export_id=None)

        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = AsyncMock()
        session_ctx.__aexit__.return_value = False

        process_variants = AsyncMock()

        with (
            patch("app.worker.runner.WorkerAsyncSessionFactory", return_value=session_ctx),
            patch("app.worker.runner.PhotoService") as photo_service_cls,
            patch("app.worker.runner.PhotoRepository"),
        ):
            photo_service_cls.return_value.process_photo_variants_by_id = process_variants
            await HeavyWorkerJobExecutor().execute_lease(lease)

        process_variants.assert_awaited_once_with("pho-1")

    @pytest.mark.asyncio
    async def test_service_error_is_wrapped_as_heavy_execution_error(self):
        from app.worker.runner import HeavyWorkerJobExecutor, HeavyWorkerJobExecutionError

        lease = _heavy_lease(job_type="export_generate", export_id="exp-1", photo_id=None)

        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = AsyncMock()
        session_ctx.__aexit__.return_value = False

        with (
            patch("app.worker.runner.WorkerAsyncSessionFactory", return_value=session_ctx),
            patch("app.worker.runner.ProjectService") as project_service_cls,
            patch("app.worker.runner.ExportService") as export_service_cls,
            patch("app.worker.runner.ExportRepository"),
            patch("app.worker.runner.ProjectRepository"),
            patch("app.worker.runner.ProposalDraftRepository"),
            patch("app.worker.runner.FinalProposalRepository"),
        ):
            project_service_cls.return_value.get_project_detail = AsyncMock(return_value=MagicMock())
            export_service_cls.return_value.process_export_by_id = AsyncMock(
                side_effect=RuntimeError("pdf engine crashed")
            )

            with pytest.raises(HeavyWorkerJobExecutionError) as exc_info:
                await HeavyWorkerJobExecutor().execute_lease(lease)

        assert exc_info.value.job_type == "export_generate"
        assert exc_info.value.export_id == "exp-1"
        assert isinstance(exc_info.value.cause, RuntimeError)

    @pytest.mark.asyncio
    async def test_invalid_payload_returns_none_without_raising(self):
        from app.worker.runner import HeavyWorkerJobExecutor

        lease = _heavy_lease(job_type="export_generate", export_id="exp-1", photo_id=None)
        bad_payload_lease = LeasedHeavyJob(
            token=lease.token,
            payload={"job_type": "unknown_type", "project_id": "proj-1"},
            raw_payload="{}",
            worker_id=lease.worker_id,
            leased_at_ms=lease.leased_at_ms,
            lease_timeout_ms=lease.lease_timeout_ms,
            expires_at_ms=lease.expires_at_ms,
        )

        # Should not raise — invalid payloads are logged and discarded
        result = await HeavyWorkerJobExecutor().execute_lease(bad_payload_lease)
        assert result is None


class TestRunHeavyJobTask:
    """Unit tests for _run_heavy_job_task ack/error lifecycle."""

    @pytest.mark.asyncio
    async def test_successful_execution_acks_heavy_lease(self):
        from app.worker import runner

        lease = _heavy_lease()
        runtime = _make_runtime(worker_heavy_concurrency=1)
        # Simulate slot acquired by _acquire_heavy_job_slot before task spawning
        await runtime.heavy_concurrency_limiter.acquire()

        ack_mock = AsyncMock(return_value=True)

        with (
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=AsyncMock()),
            patch("app.worker.runner.ack_heavy_job", new=ack_mock),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
        ):
            await runner._run_heavy_job_task(runtime, lease)

        ack_mock.assert_awaited_once_with(runtime.redis, lease)
        assert runtime.heavy_concurrency_limiter._value == 1  # slot released back

    @pytest.mark.asyncio
    async def test_execution_error_still_acks_and_releases_slot(self):
        from app.worker import runner

        lease = _heavy_lease()
        runtime = _make_runtime(worker_heavy_concurrency=1)
        await runtime.heavy_concurrency_limiter.acquire()

        ack_mock = AsyncMock(return_value=True)
        exec_error = runner.HeavyWorkerJobExecutionError(
            job_type="export_generate",
            project_id="proj-1",
            organization_id="org-1",
            export_id="exp-1",
            photo_id=None,
            cause=RuntimeError("boom"),
        )

        with (
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=AsyncMock(side_effect=exec_error)),
            patch("app.worker.runner.ack_heavy_job", new=ack_mock),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
        ):
            await runner._run_heavy_job_task(runtime, lease)

        ack_mock.assert_awaited_once_with(runtime.redis, lease)
        assert runtime.heavy_concurrency_limiter._value == 1

    @pytest.mark.asyncio
    async def test_lost_lease_on_ack_is_logged_without_raising(self):
        from app.worker import runner

        lease = _heavy_lease()
        runtime = _make_runtime(worker_heavy_concurrency=1)
        await runtime.heavy_concurrency_limiter.acquire()

        with (
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=AsyncMock()),
            patch(
                "app.worker.runner.ack_heavy_job",
                new=AsyncMock(side_effect=LostHeavyJobLeaseError("lease stolen")),
            ),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
        ):
            # Must not propagate
            await runner._run_heavy_job_task(runtime, lease)

        # Slot must still be released even when ack raises LostHeavyJobLeaseError
        assert runtime.heavy_concurrency_limiter._value == 1

    @pytest.mark.asyncio
    async def test_ack_skipped_is_logged_when_ack_returns_false(self):
        from app.worker import runner

        lease = _heavy_lease()
        runtime = _make_runtime(worker_heavy_concurrency=1)
        await runtime.heavy_concurrency_limiter.acquire()

        with (
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=AsyncMock()),
            patch("app.worker.runner.ack_heavy_job", new=AsyncMock(return_value=False)),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
        ):
            await runner._run_heavy_job_task(runtime, lease)

        assert runtime.heavy_concurrency_limiter._value == 1


class TestRunHeavyLeaseReaper:
    """Unit tests for _run_heavy_lease_reaper_if_due."""

    @pytest.mark.asyncio
    async def test_skipped_when_heavy_concurrency_is_zero(self):
        from app.worker import runner

        runtime = _make_runtime(worker_heavy_concurrency=0, last_heavy_lease_reap=0.0)

        get_expired = AsyncMock()
        with patch("app.worker.runner.get_expired_heavy_job_leases", new=get_expired):
            await runner._run_heavy_lease_reaper_if_due(runtime, now_monotonic=9999.0)

        get_expired.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skipped_when_interval_not_elapsed(self):
        from app.worker import runner

        now = time.monotonic()
        runtime = _make_runtime(
            worker_heavy_concurrency=1,
            heavy_lease_reap_interval_seconds=30,
            last_heavy_lease_reap=now,
        )

        get_expired = AsyncMock()
        with patch("app.worker.runner.get_expired_heavy_job_leases", new=get_expired):
            await runner._run_heavy_lease_reaper_if_due(runtime, now_monotonic=now + 10)

        get_expired.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_lease_is_requeued(self):
        from app.worker import runner

        runtime = _make_runtime(
            worker_heavy_concurrency=1,
            heavy_lease_reap_interval_seconds=30,
            last_heavy_lease_reap=0.0,
        )
        expired = _heavy_lease()
        requeue_mock = AsyncMock(return_value=True)

        with (
            patch("app.worker.runner.get_expired_heavy_job_leases", new=AsyncMock(return_value=[expired])),
            patch("app.worker.runner.requeue_expired_heavy_job", new=requeue_mock),
            patch("app.worker.runner.drop_expired_heavy_job", new=AsyncMock(return_value=False)),
        ):
            await runner._run_heavy_lease_reaper_if_due(runtime, now_monotonic=9999.0)

        requeue_mock.assert_awaited_once_with(runtime.redis, expired)

    @pytest.mark.asyncio
    async def test_failed_requeue_falls_back_to_drop(self):
        from app.worker import runner

        runtime = _make_runtime(
            worker_heavy_concurrency=1,
            heavy_lease_reap_interval_seconds=30,
            last_heavy_lease_reap=0.0,
        )
        expired = _heavy_lease()
        drop_mock = AsyncMock(return_value=True)

        with (
            patch("app.worker.runner.get_expired_heavy_job_leases", new=AsyncMock(return_value=[expired])),
            patch("app.worker.runner.requeue_expired_heavy_job", new=AsyncMock(return_value=False)),
            patch("app.worker.runner.drop_expired_heavy_job", new=drop_mock),
        ):
            await runner._run_heavy_lease_reaper_if_due(runtime, now_monotonic=9999.0)

        drop_mock.assert_awaited_once_with(runtime.redis, expired)

    @pytest.mark.asyncio
    async def test_reaper_exception_does_not_crash_loop(self):
        from app.worker import runner

        runtime = _make_runtime(
            worker_heavy_concurrency=1,
            heavy_lease_reap_interval_seconds=30,
            last_heavy_lease_reap=0.0,
        )
        expired = _heavy_lease()

        with (
            patch("app.worker.runner.get_expired_heavy_job_leases", new=AsyncMock(return_value=[expired])),
            patch("app.worker.runner.requeue_expired_heavy_job", new=AsyncMock(side_effect=OSError("redis gone"))),
            patch("app.worker.runner.drop_expired_heavy_job", new=AsyncMock(side_effect=OSError("redis gone"))),
        ):
            # Must not propagate
            await runner._run_heavy_lease_reaper_if_due(runtime, now_monotonic=9999.0)


class TestHeavyWorkerLaneSeparation:
    """Smoke tests: heavy workload lane does not share slots with analysis lane."""

    @pytest.mark.asyncio
    async def test_heavy_slot_disabled_when_worker_heavy_concurrency_zero(self):
        from app.worker import runner

        runtime = _make_runtime(worker_heavy_concurrency=0)

        dequeue_heavy = AsyncMock()
        with (
            patch("app.worker.runner.dequeue_analysis_job", new=AsyncMock(return_value=None)),
            patch("app.worker.runner.dequeue_heavy_job", new=dequeue_heavy),
            patch("app.worker.runner._run_export_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_photo_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()),
            patch("app.worker.runner._drain_finished_tasks", new=AsyncMock()),
            patch("app.worker.runner._run_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_heavy_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner.promote_scheduled_analysis_jobs", new=AsyncMock(return_value=0)),
            patch("app.worker.runner.asyncio.sleep", new=AsyncMock()),
        ):
            await runner._run_one_iteration(runtime)

        dequeue_heavy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heavy_semaphore_is_independent_of_analysis_semaphore(self):
        """Heavy slot can be acquired even when analysis semaphore is exhausted."""
        from app.worker import runner

        heavy_lease = _heavy_lease(job_type="export_generate", export_id="exp-1", photo_id=None)

        release = asyncio.Event()

        async def _block_heavy(_lease):
            await release.wait()

        runtime = _make_runtime(worker_heavy_concurrency=2)
        # Exhaust the analysis semaphore to prove heavy lane is unaffected
        await runtime.concurrency_limiter.acquire()

        heavy_exec = AsyncMock(side_effect=_block_heavy)

        with (
            patch("app.worker.runner.dequeue_analysis_job", new=AsyncMock(return_value=None)),
            patch("app.worker.runner.dequeue_heavy_job", new=AsyncMock(return_value=heavy_lease)),
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=heavy_exec),
            patch("app.worker.runner.ack_heavy_job", new=AsyncMock(return_value=True)),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
            patch("app.worker.runner._run_export_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_photo_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()),
            patch("app.worker.runner._drain_finished_tasks", new=AsyncMock()),
            patch("app.worker.runner._run_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_heavy_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner.promote_scheduled_analysis_jobs", new=AsyncMock(return_value=0)),
            patch("app.worker.runner._seconds_until_next_heartbeat", return_value=0),
        ):
            await runner._run_one_iteration(runtime)

        assert len(runtime.inflight_heavy_tasks) == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(*list(runtime.inflight_heavy_tasks)), timeout=1)

    @pytest.mark.asyncio
    async def test_both_lanes_run_concurrently_in_same_iteration(self):
        """Analysis job and heavy job can both be spawned in a single iteration."""
        from app.worker import runner

        analysis_lease = _lease()
        heavy_lease = _heavy_lease(job_type="photo_variant_processing", photo_id="pho-1", export_id=None)
        gate = asyncio.Event()

        async def _block(*_args, **_kwargs):
            await gate.wait()

        runtime = _make_runtime(worker_heavy_concurrency=1)

        with (
            patch("app.worker.runner.dequeue_analysis_job", new=AsyncMock(return_value=analysis_lease)),
            patch("app.worker.runner.dequeue_heavy_job", new=AsyncMock(return_value=heavy_lease)),
            patch("app.worker.runner.WorkerJobExecutor.execute_lease", new=AsyncMock(side_effect=_block)),
            patch("app.worker.runner.HeavyWorkerJobExecutor.execute_lease", new=AsyncMock(side_effect=_block)),
            patch("app.worker.runner.ack_analysis_job", new=AsyncMock(return_value=True)),
            patch("app.worker.runner.ack_heavy_job", new=AsyncMock(return_value=True)),
            patch("app.worker.runner.renew_analysis_job_lease", new=AsyncMock()),
            patch("app.worker.runner.renew_heavy_job_lease", new=AsyncMock()),
            patch("app.worker.runner._run_export_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_photo_cleanup_if_due", new=AsyncMock()),
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()),
            patch("app.worker.runner._drain_finished_tasks", new=AsyncMock()),
            patch("app.worker.runner._run_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner._run_heavy_lease_reaper_if_due", new=AsyncMock()),
            patch("app.worker.runner.promote_scheduled_analysis_jobs", new=AsyncMock(return_value=0)),
            patch("app.worker.runner._build_worker_analysis_service", return_value=AsyncMock()),
        ):
            await runner._run_one_iteration(runtime)

        # Both lanes spawned exactly one task each
        assert len(runtime.inflight_tasks) == 1
        assert len(runtime.inflight_heavy_tasks) == 1

        gate.set()
        all_tasks = list(runtime.inflight_tasks) + list(runtime.inflight_heavy_tasks)
        await asyncio.wait_for(asyncio.gather(*all_tasks, return_exceptions=True), timeout=2)
