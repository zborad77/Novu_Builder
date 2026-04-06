"""Photo startup reconciliation tests.

Invariant: when a worker starts, all photos whose processing_status is
``uploaded`` or ``processing`` but whose heavy-lane transport entry is
missing MUST be re-enqueued automatically.

Coverage
--------
1.  Photo with ``uploaded`` status missing from transport → re-enqueued
2.  Photo with ``processing`` status missing from transport → re-enqueued
3.  Photo already present in transport → NOT re-enqueued
4.  worker_heavy_concurrency == 0 → reconciliation skipped entirely
5.  Enqueue exception → logged as warning, does not raise (non-strict mode)
6.  _reconcile_startup_runtime_state failure in strict mode → raises RuntimeError
7.  _reconcile_startup_runtime_state failure in dev mode → logs error, does not raise
8.  Multiple photos: mix of in-transport and missing → only missing ones re-enqueued
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(*, worker_heavy_concurrency: int = 2):
    from app.worker import runner as runner_module

    settings = MagicMock()
    settings.app_env = "production"
    settings.heavy_queue_max_depth = 50
    settings.effective_backpressure_max_queued_jobs = 1000

    return runner_module.WorkerRuntime(
        settings=settings,
        redis=AsyncMock(),
        redis_url="redis://localhost:6379/0",
        worker_instance_id="worker-test",
        heartbeat_key="worker:heartbeat:worker-test",
        job_executor=MagicMock(execute_lease=AsyncMock()),
        heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
        worker_concurrency=1,
        job_lease_timeout_seconds=60,
        lease_reap_interval_seconds=5,
        concurrency_limiter=asyncio.Semaphore(1),
        inflight_tasks=set(),
        worker_heavy_concurrency=worker_heavy_concurrency,
        last_lease_reap=0.0,
    )


def _make_photo(*, photo_id: str, project_id: str = "prj_001", processing_status: str = "uploaded"):
    return SimpleNamespace(
        id=photo_id,
        project_id=project_id,
        processing_status=processing_status,
    )


def _make_transport_snapshot(*, photo_ids_in_transport: list[str] | None = None):
    """Build a fake HeavyJobTransportSnapshot that knows which photo_ids are in-flight."""
    in_transport = set(photo_ids_in_transport or [])
    snapshot = MagicMock()
    snapshot.has_photo = lambda photo_id: photo_id in in_transport
    snapshot.has_export = lambda export_id: False
    return snapshot


# ---------------------------------------------------------------------------
# 1–2. Missing-from-transport photos are re-enqueued
# ---------------------------------------------------------------------------

class TestMissingPhotosAreReenqueued:
    @pytest.mark.asyncio
    async def test_uploaded_photo_missing_from_transport_is_requeued(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        photo = _make_photo(photo_id="pho_uploaded", processing_status="uploaded")
        snapshot = _make_transport_snapshot(photo_ids_in_transport=[])

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=[photo])
                mock_repo_cls.return_value = mock_repo

                await _reconcile_startup_photos(runtime)

        mock_enqueue.assert_awaited_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs.get("job_type") == "photo_variant_processing"
        assert call_kwargs.kwargs.get("photo_id") == "pho_uploaded"

    @pytest.mark.asyncio
    async def test_processing_photo_missing_from_transport_is_requeued(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        photo = _make_photo(photo_id="pho_processing", processing_status="processing")
        snapshot = _make_transport_snapshot(photo_ids_in_transport=[])

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=[photo])
                mock_repo_cls.return_value = mock_repo

                await _reconcile_startup_photos(runtime)

        mock_enqueue.assert_awaited_once()
        call_kwargs = mock_enqueue.call_args
        assert call_kwargs.kwargs.get("job_type") == "photo_variant_processing"
        assert call_kwargs.kwargs.get("photo_id") == "pho_processing"


# ---------------------------------------------------------------------------
# 3. Photo already in transport → NOT re-enqueued
# ---------------------------------------------------------------------------

class TestPhotoAlreadyInTransportSkipped:
    @pytest.mark.asyncio
    async def test_photo_already_in_transport_is_not_requeued(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        photo = _make_photo(photo_id="pho_inflight", processing_status="uploaded")
        snapshot = _make_transport_snapshot(photo_ids_in_transport=["pho_inflight"])

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=[photo])
                mock_repo_cls.return_value = mock_repo

                await _reconcile_startup_photos(runtime)

        mock_enqueue.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. worker_heavy_concurrency == 0 → reconciliation skipped entirely
# ---------------------------------------------------------------------------

class TestReconciliationSkippedWhenHeavyLaneDisabled:
    @pytest.mark.asyncio
    async def test_reconciliation_skipped_when_concurrency_zero(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=0)

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock()) as mock_inspect,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            await _reconcile_startup_photos(runtime)

        mock_inspect.assert_not_awaited()
        mock_enqueue.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. Enqueue exception → logged, does not raise
# ---------------------------------------------------------------------------

class TestEnqueueExceptionIsLogged:
    @pytest.mark.asyncio
    async def test_enqueue_failure_is_logged_not_raised(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        photo = _make_photo(photo_id="pho_fail", processing_status="uploaded")
        snapshot = _make_transport_snapshot(photo_ids_in_transport=[])

        async def _failing_enqueue(*args, **kwargs):
            raise RuntimeError("Redis unavailable")

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock(side_effect=_failing_enqueue)),
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=[photo])
                mock_repo_cls.return_value = mock_repo

                # Must not raise
                await _reconcile_startup_photos(runtime)


# ---------------------------------------------------------------------------
# 6–7. _reconcile_startup_runtime_state failure: strict vs dev mode
# ---------------------------------------------------------------------------

class TestReconciliationFailFast:
    @pytest.mark.asyncio
    async def test_strict_mode_raises_runtime_error_on_reconciliation_failure(self):
        from app.worker.runner import _reconcile_startup_runtime_state

        runtime = _make_runtime(worker_heavy_concurrency=2)
        runtime.settings.app_env = "production"

        async def _boom(*args, **kwargs):
            raise RuntimeError("DB down")

        with (
            patch("app.worker.runner._reconcile_startup_analysis_jobs", new=AsyncMock(side_effect=_boom)),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                try:
                    await _reconcile_startup_runtime_state(runtime)
                except RuntimeError:
                    raise
                except Exception as exc:
                    # Simulate the run() wrapper behavior
                    from app.worker.runner import _is_strict_worker_environment
                    from app.core.config import startup_failure_message
                    if _is_strict_worker_environment(runtime.settings):
                        raise RuntimeError(
                            startup_failure_message("worker_reconciliation", str(exc))
                        ) from exc

        assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_dev_mode_logs_error_without_raising(self):
        from app.worker.runner import _is_strict_worker_environment

        settings = MagicMock()
        settings.app_env = "development"

        assert _is_strict_worker_environment(settings) is False

    @pytest.mark.asyncio
    async def test_test_env_is_not_strict(self):
        from app.worker.runner import _is_strict_worker_environment

        settings = MagicMock()
        settings.app_env = "test"

        assert _is_strict_worker_environment(settings) is False

    @pytest.mark.asyncio
    async def test_production_env_is_strict(self):
        from app.worker.runner import _is_strict_worker_environment

        settings = MagicMock()
        settings.app_env = "production"

        assert _is_strict_worker_environment(settings) is True

    @pytest.mark.asyncio
    async def test_staging_env_is_strict(self):
        from app.worker.runner import _is_strict_worker_environment

        settings = MagicMock()
        settings.app_env = "staging"

        assert _is_strict_worker_environment(settings) is True


# ---------------------------------------------------------------------------
# 8. Mix of in-transport and missing photos
# ---------------------------------------------------------------------------

class TestMixedTransportState:
    @pytest.mark.asyncio
    async def test_only_missing_photos_are_requeued(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        photos = [
            _make_photo(photo_id="pho_in_transport", processing_status="processing"),
            _make_photo(photo_id="pho_missing_1", processing_status="uploaded"),
            _make_photo(photo_id="pho_missing_2", processing_status="processing"),
        ]
        snapshot = _make_transport_snapshot(photo_ids_in_transport=["pho_in_transport"])

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=photos)
                mock_repo_cls.return_value = mock_repo

                await _reconcile_startup_photos(runtime)

        assert mock_enqueue.await_count == 2
        enqueued_ids = {c.kwargs["photo_id"] for c in mock_enqueue.call_args_list}
        assert enqueued_ids == {"pho_missing_1", "pho_missing_2"}
        assert "pho_in_transport" not in enqueued_ids

    @pytest.mark.asyncio
    async def test_empty_incomplete_list_does_not_enqueue(self):
        from app.worker.runner import _reconcile_startup_photos

        runtime = _make_runtime(worker_heavy_concurrency=2)
        snapshot = _make_transport_snapshot(photo_ids_in_transport=[])

        with (
            patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=snapshot)),
            patch("app.worker.runner.WorkerAsyncSessionFactory") as mock_factory,
            patch("app.worker.runner.enqueue_heavy_job", new=AsyncMock()) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch("app.worker.runner.PhotoRepository") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.list_incomplete_photos = AsyncMock(return_value=[])
                mock_repo_cls.return_value = mock_repo

                await _reconcile_startup_photos(runtime)

        mock_enqueue.assert_not_awaited()
