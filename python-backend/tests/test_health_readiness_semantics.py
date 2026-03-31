from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Response


@pytest.fixture(autouse=True)
def _reset_readiness_cache():
    from app.api.routes.system import (
        _clear_operational_metrics_cache,
        _clear_readiness_db_cache,
        _clear_readiness_storage_cache,
    )
    from app.main import app as fastapi_app

    _clear_readiness_db_cache(fastapi_app)
    _clear_readiness_storage_cache(fastapi_app)
    _clear_operational_metrics_cache(fastapi_app)
    yield
    _clear_readiness_db_cache(fastapi_app)
    _clear_readiness_storage_cache(fastapi_app)
    _clear_operational_metrics_cache(fastapi_app)


@pytest.mark.asyncio
async def test_health_is_minimal_and_not_coupled_to_dependency_checks(app_client):
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__.side_effect = RuntimeError("db unavailable")
    failing_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.routes.system.AsyncSessionFactory", return_value=failing_ctx):
        response = await app_client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "python-backend"}


@pytest.mark.asyncio
async def test_ready_is_minimal_when_service_is_ready(app_client):
    response = await app_client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "python-backend"}


@pytest.mark.asyncio
async def test_processing_ready_returns_strict_ready_when_worker_path_is_healthy(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = SimpleNamespace(
        alive=True,
        last_seen_at="2026-03-31T10:00:00+00:00",
        alive_instances=1,
        seen_instances=1,
    )

    original_job_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.job_queue = object()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready/processing?strict=1")
    finally:
        fastapi_app.state.job_queue = original_job_queue

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "python-backend",
        "apiReady": True,
        "jobProcessingReady": True,
        "workerState": "ready",
        "queueState": "ready",
        "graceActive": False,
        "strict": True,
    }


@pytest.mark.asyncio
async def test_processing_ready_surfaces_degraded_queue_state_when_failover_is_active(app_client):
    from app.main import app as fastapi_app

    class _DegradedQueue:
        def runtime_status(self):
            return SimpleNamespace(
                state="degraded",
                mode="failover",
                candidate_count=2,
                active_url="redis://:***@secondary:6379/0",
                degraded=True,
                last_error="primary down",
                last_failover_at="2026-03-31T10:00:00+00:00",
            )

    worker_snapshot = SimpleNamespace(
        alive=True,
        last_seen_at="2026-03-31T10:00:00+00:00",
        alive_instances=1,
        seen_instances=1,
    )

    original_job_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.job_queue = _DegradedQueue()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready/processing?strict=1")
    finally:
        fastapi_app.state.job_queue = original_job_queue

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["queueState"] == "degraded"


@pytest.mark.asyncio
async def test_processing_ready_uses_grace_window_for_short_worker_gap(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = SimpleNamespace(
        alive=False,
        last_seen_at=None,
        alive_instances=0,
        seen_instances=0,
    )
    original_started = fastapi_app.state.readiness_started_at_monotonic
    original_job_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.readiness_started_at_monotonic = 100.0
    fastapi_app.state.job_queue = object()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
            patch("app.api.routes.system._readiness_now", return_value=120.0),
        ):
            response = await app_client.get("/api/v1/ready/processing")
    finally:
        fastapi_app.state.readiness_started_at_monotonic = original_started
        fastapi_app.state.job_queue = original_job_queue

    assert response.status_code == 200
    assert response.json() == {
        "status": "warming_up",
        "service": "python-backend",
        "apiReady": True,
        "jobProcessingReady": True,
        "workerState": "missing",
        "queueState": "ready",
        "graceActive": True,
        "strict": False,
    }


@pytest.mark.asyncio
async def test_processing_ready_strict_mode_rejects_stale_worker_even_during_grace(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = SimpleNamespace(
        alive=False,
        last_seen_at="2026-03-31T09:58:00+00:00",
        alive_instances=0,
        seen_instances=1,
    )
    original_started = fastapi_app.state.readiness_started_at_monotonic
    original_job_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.readiness_started_at_monotonic = 100.0
    fastapi_app.state.job_queue = object()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
            patch("app.api.routes.system._readiness_now", return_value=120.0),
        ):
            response = await app_client.get("/api/v1/ready/processing?strict=1")
    finally:
        fastapi_app.state.readiness_started_at_monotonic = original_started
        fastapi_app.state.job_queue = original_job_queue

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "python-backend",
        "apiReady": True,
        "jobProcessingReady": False,
        "workerState": "stale",
        "queueState": "ready",
        "graceActive": True,
        "strict": True,
    }


@pytest.mark.asyncio
async def test_ready_returns_503_when_startup_checks_are_not_ready(app_client):
    from app.main import app as fastapi_app

    original_checks = deepcopy(fastapi_app.state.startup_checks)
    fastapi_app.state.startup_checks = {
        "database": "ok",
        "schema": "pending",
        "storage": "ok",
    }
    try:
        response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.startup_checks = original_checks

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "python-backend"}


@pytest.mark.asyncio
async def test_ready_returns_503_when_database_probe_fails(app_client):
    failing_ctx = AsyncMock()
    failing_ctx.__aenter__.side_effect = RuntimeError("db unavailable")
    failing_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.routes.system.AsyncSessionFactory", return_value=failing_ctx):
        response = await app_client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "python-backend"}


@pytest.mark.asyncio
async def test_ready_returns_503_when_storage_probe_fails(app_client):
    with patch("app.api.routes.system.verify_storage_health", new=AsyncMock(side_effect=RuntimeError("s3 down"))):
        response = await app_client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "service": "python-backend"}


@pytest.mark.asyncio
async def test_health_stays_200_when_readiness_is_failing(app_client):
    from app.main import app as fastapi_app

    original_checks = deepcopy(fastapi_app.state.startup_checks)
    fastapi_app.state.startup_checks = {
        "database": "pending",
        "schema": "pending",
        "storage": "pending",
    }
    try:
        health = await app_client.get("/api/v1/health")
        ready = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.startup_checks = original_checks

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "service": "python-backend"}
    assert ready.status_code == 503
    assert ready.json() == {"status": "not_ready", "service": "python-backend"}


@pytest.mark.asyncio
async def test_internal_health_returns_503_when_service_is_not_ready():
    from app.api.routes.system import health_internal
    from app.schemas.auth import AuthUserRead

    mock_request = AsyncMock()
    mock_request.app.state.startup_checks = {
        "database": "ok",
        "schema": "pending",
        "storage": "ok",
    }
    mock_request.app.state.job_queue = None
    response = Response()

    current_user = AuthUserRead(
        id="sa-1",
        email="sa@test.com",
        fullName="SA",
        role="superadmin",
        isActive=True,
        organizationId="org-1",
        isSuperAdmin=True,
        impersonatedBy=None,
    )

    with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(side_effect=[
            AsyncMock(),
            SimpleNamespace(scalar_one=lambda: 0),
            SimpleNamespace(scalar_one=lambda: 0),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ])
        mock_session.scalar = AsyncMock(return_value=None)
        mock_factory.return_value = mock_session

        body = await health_internal(
            request=mock_request,
            response=response,
            _=current_user,
        )

    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["ready"] is False
    assert body["apiReady"] is False
    assert body["jobProcessingReady"] is False
    assert body["storage"] in {"ok", "error"}


@pytest.mark.asyncio
async def test_internal_health_omits_debug_flag_and_keeps_internal_details():
    from app.api.routes.system import health_internal
    from app.schemas.auth import AuthUserRead

    mock_request = AsyncMock()
    mock_request.app.state.startup_checks = {
        "database": "ok",
        "schema": "ok",
        "storage": "ok",
    }
    mock_request.app.state.job_queue = object()
    response = Response()

    current_user = AuthUserRead(
        id="sa-1",
        email="sa@test.com",
        fullName="SA",
        role="superadmin",
        isActive=True,
        organizationId="org-1",
        isSuperAdmin=True,
        impersonatedBy=None,
    )

    worker_snapshot = SimpleNamespace(
        alive=True,
        last_seen_at="2026-03-31T10:00:00+00:00",
        alive_instances=1,
        seen_instances=1,
    )

    with (
        patch("app.api.routes.system.AsyncSessionFactory") as mock_factory,
        patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
        patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(side_effect=[
            AsyncMock(),
            SimpleNamespace(scalar_one=lambda: 0),
            SimpleNamespace(scalar_one=lambda: 0),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ])
        mock_session.scalar = AsyncMock(return_value=None)
        mock_factory.return_value = mock_session

        body = await health_internal(
            request=mock_request,
            response=response,
            _=current_user,
        )

    assert response.status_code == 200
    assert "debug" not in body
    assert "startupChecks" in body
    assert "worker" in body
    assert body["apiReady"] is True
    assert body["jobProcessingReady"] is True


@pytest.mark.asyncio
async def test_readiness_db_cache_hits_within_ttl():
    from app.api.routes.system import _database_ready_cached

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    db_probe = AsyncMock(side_effect=[True, False])

    with (
        patch("app.api.routes.system._database_ready", db_probe),
        patch("app.api.routes.system._readiness_now", side_effect=[100.0, 100.0, 101.0]),
    ):
        first = await _database_ready_cached(request)
        second = await _database_ready_cached(request)

    assert first is True
    assert second is True
    assert db_probe.await_count == 1


@pytest.mark.asyncio
async def test_readiness_db_cache_refreshes_after_ttl_expiry():
    from app.api.routes.system import _database_ready_cached

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    db_probe = AsyncMock(side_effect=[True, True])

    with (
        patch("app.api.routes.system._database_ready", db_probe),
        patch("app.api.routes.system._readiness_now", side_effect=[200.0, 200.0, 202.5, 202.5]),
    ):
        first = await _database_ready_cached(request)
        second = await _database_ready_cached(request)

    assert first is True
    assert second is True
    assert db_probe.await_count == 2


@pytest.mark.asyncio
async def test_readiness_db_cache_returns_non_ready_after_expiry_when_db_fails():
    from app.api.routes.system import _database_ready_cached

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    db_probe = AsyncMock(side_effect=[True, False])

    with (
        patch("app.api.routes.system._database_ready", db_probe),
        patch("app.api.routes.system._readiness_now", side_effect=[300.0, 300.0, 302.5, 302.5]),
    ):
        first = await _database_ready_cached(request)
        second = await _database_ready_cached(request)

    assert first is True
    assert second is False
    assert db_probe.await_count == 2


@pytest.mark.asyncio
async def test_ready_reuses_fresh_operational_snapshot_without_extra_db_probe():
    from app.api.routes.system import (
        _OperationalMetricsSnapshot,
        _WorkerHeartbeatSnapshot,
        _database_ready_cached,
        _get_operational_metrics_cache,
    )

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    operational_cache = _get_operational_metrics_cache(request)
    operational_cache.snapshot = _OperationalMetricsSnapshot(
        db_alive=True,
        jobs_running=2,
        jobs_queued=3,
        queue_length=3,
        processing_jobs=2,
        job_stuck_max_age_seconds=0.0,
        worker=_WorkerHeartbeatSnapshot(
            alive=True,
            last_seen_at="2026-03-30T00:00:00+00:00",
            alive_instances=1,
            seen_instances=1,
        ),
        queue_monitoring_available=True,
    )
    operational_cache.expires_at_monotonic = 105.0
    db_probe = AsyncMock(return_value=False)

    with (
        patch("app.api.routes.system._database_ready", db_probe),
        patch("app.api.routes.system._readiness_now", side_effect=[100.0, 100.0]),
    ):
        ready = await _database_ready_cached(request)

    assert ready is True
    db_probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_ready_cache_returns_failed_after_expiry():
    from app.api.routes.system import _storage_ready_cached

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    storage_probe = AsyncMock(side_effect=[True, False])

    with (
        patch("app.api.routes.system._storage_ready", storage_probe),
        patch("app.api.routes.system._readiness_now", side_effect=[400.0, 400.0, 402.5, 402.5]),
    ):
        first = await _storage_ready_cached(request)
        second = await _storage_ready_cached(request)

    assert first is True
    assert second is False
    assert storage_probe.await_count == 2
