import asyncio
import inspect
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.queue import InvalidAnalysisJobPayloadError


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

        with patch("app.worker.runner.build_redis_client_from_settings", return_value=object()) as build_client:
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

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }

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
            patch("app.worker.runner.WorkerJobExecutor.execute_payload", new=AsyncMock()) as execute_payload,
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

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
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
                "app.worker.runner.WorkerJobExecutor.execute_payload",
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


class TestWorkerConcurrencyControl:
    @pytest.mark.asyncio
    async def test_run_one_iteration_spawns_background_jobs_up_to_configured_limit(self):
        from app.worker import runner

        payload_one = {
            "job_id": "job_1",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        payload_two = {
            "job_id": "job_2",
            "project_id": "proj-2",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        started = asyncio.Event()
        release = asyncio.Event()
        started_jobs = 0

        async def _execute_payload(payload):
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
            job_executor=MagicMock(execute_payload=AsyncMock(side_effect=_execute_payload)),
            worker_concurrency=2,
            concurrency_limiter=asyncio.Semaphore(2),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
        )

        with patch(
            "app.worker.runner.dequeue_analysis_job",
            new=AsyncMock(side_effect=[payload_one, payload_two]),
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
            job_executor=MagicMock(execute_payload=AsyncMock()),
            worker_concurrency=1,
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
    async def test_run_cancels_inflight_tasks_on_shutdown_without_leaking(self):
        from app.worker import runner

        settings = MagicMock()
        settings.redis_url = "redis://:secret@localhost:6379/0"
        settings.ai_analysis_provider = "mock"
        settings.worker_concurrency = 2

        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.aclose = AsyncMock()

        valid_payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        task_started = asyncio.Event()
        task_cancelled = asyncio.Event()
        dequeue_calls = 0

        async def _execute_payload(_payload):
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
            patch(
                "app.worker.runner.WorkerJobExecutor.execute_payload",
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
            job_executor=MagicMock(execute_payload=AsyncMock()),
            worker_concurrency=1,
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
    async def test_run_one_iteration_runs_export_cleanup_before_dequeue(self):
        from app.worker import runner

        runtime = runner.WorkerRuntime(
            settings=MagicMock(),
            redis=AsyncMock(),
            redis_url="redis://:secret@localhost:6379/0",
            worker_instance_id="worker-a",
            heartbeat_key="worker:heartbeat:worker-a",
            job_executor=MagicMock(execute_payload=AsyncMock()),
            worker_concurrency=1,
            concurrency_limiter=asyncio.Semaphore(1),
            inflight_tasks=set(),
            last_heartbeat=time.monotonic(),
        )

        with (
            patch("app.worker.runner._run_export_cleanup_if_due", new=AsyncMock()) as cleanup,
            patch("app.worker.runner._write_heartbeat_if_due", new=AsyncMock()) as heartbeat,
            patch("app.worker.runner._drain_finished_tasks", new=AsyncMock()) as drain,
            patch("app.worker.runner._acquire_job_slot", new=AsyncMock(return_value=False)) as acquire,
        ):
            await runner._run_one_iteration(runtime)

        cleanup.assert_awaited_once_with(runtime)
        heartbeat.assert_awaited_once_with(runtime)
        drain.assert_awaited_once_with(runtime)
        acquire.assert_awaited_once_with(runtime)
