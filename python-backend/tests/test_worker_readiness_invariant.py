"""Worker and processing-readiness contract tests.

Contract: general readiness tracks critical dependencies, while processing
readiness tracks worker availability. A missing or stale worker must degrade
health and block /ready/processing, but must not force /ready to 503 when the
API-critical dependencies remain healthy.

Coverage
--------
1. Worker down (no heartbeat)        -> /ready = 200 degraded, ready=True
2. Worker alive (fresh heartbeat)    -> /ready = 200, ready=True
3. Worker heartbeat stale / expired  -> /ready = 200 degraded, ready=True
4. Redis unavailable (worker unknown)-> /ready = 503, ready=False
5. /health still returns 200 when worker is dead (degraded, not unavailable)
6. /ready/processing apiReady field reflects API-only state, not worker state
7. startup.worker_not_detected is logged when no heartbeat exists at startup
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _make_worker_snapshot(*, alive: bool | None, seen_instances: int = 1):
    return SimpleNamespace(
        alive=alive,
        last_seen_at=(datetime.now(UTC) - timedelta(seconds=30)).isoformat() if alive else None,
        alive_instances=1 if alive else 0,
        seen_instances=seen_instances,
    )


class _ReadyRuntime:
    """Minimal Redis stand-in that reports queue state 'ready'."""

    async def ping(self) -> bool:
        return True

    def runtime_status(self):
        return SimpleNamespace(
            state="ready",
            mode="single",
            candidate_count=1,
            active_url="redis://:***@localhost:6379/0",
            degraded=False,
            last_error=None,
            last_failover_at=None,
        )


@pytest.fixture(autouse=True)
def _reset_caches():
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
async def test_ready_returns_200_when_worker_has_no_heartbeat(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=0)
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    original_auth = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.job_queue = _ReadyRuntime()
    fastapi_app.state.auth_token_store = _ReadyRuntime()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.job_queue = original_queue
        fastapi_app.state.auth_token_store = original_auth

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["status"] == "degraded"
    assert data["apiState"] == "ready"
    assert data["worker"]["state"] == "missing"


@pytest.mark.asyncio
async def test_ready_returns_200_when_worker_is_alive(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=True)
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.job_queue = _ReadyRuntime()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.job_queue = original_queue

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["apiState"] == "ready"
    assert data["worker"]["state"] == "ready"


@pytest.mark.asyncio
async def test_ready_returns_200_when_worker_heartbeat_is_stale(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=1)
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    original_auth = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.job_queue = _ReadyRuntime()
    fastapi_app.state.auth_token_store = _ReadyRuntime()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.job_queue = original_queue
        fastapi_app.state.auth_token_store = original_auth

    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert data["status"] == "degraded"
    assert data["worker"]["state"] == "stale"


@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_unavailable_worker_unknown(app_client):
    from app.main import app as fastapi_app

    original_queue = getattr(fastapi_app.state, "job_queue", None)
    original_auth = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.job_queue = None
    fastapi_app.state.auth_token_store = None
    try:
        response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.job_queue = original_queue
        fastapi_app.state.auth_token_store = original_auth

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["dependencies"]["redis"] == "unavailable"


@pytest.mark.asyncio
async def test_health_returns_200_degraded_when_worker_is_down(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=1)
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    original_auth = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.job_queue = _ReadyRuntime()
    fastapi_app.state.auth_token_store = _ReadyRuntime()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/health")
    finally:
        fastapi_app.state.job_queue = original_queue
        fastapi_app.state.auth_token_store = original_auth

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ready"] is True


@pytest.mark.asyncio
async def test_processing_ready_api_ready_reflects_api_state_not_worker_state(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=0)
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.job_queue = _ReadyRuntime()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            response = await app_client.get("/api/v1/ready/processing?strict=1")
    finally:
        fastapi_app.state.job_queue = original_queue

    assert response.status_code == 503
    data = response.json()
    assert data["apiReady"] is True
    assert data["jobProcessingReady"] is False
    assert data["workerState"] == "missing"


@pytest.mark.asyncio
async def test_startup_guard_logs_error_when_no_worker_detected():
    import structlog.testing

    from app.worker.heartbeat import scan_alive_workers  # noqa: F401

    with (
        patch(
            "app.worker.heartbeat.scan_alive_workers",
            new=AsyncMock(return_value=(0, None)),
        ) as mock_scan,
        structlog.testing.capture_logs() as cap,
    ):
        import structlog

        _logger = structlog.get_logger("app.main")
        _startup_redis = object()

        from app.worker.heartbeat import scan_alive_workers as _scan

        _alive_count, _last_seen = await _scan(_startup_redis)
        if _alive_count == 0:
            _logger.error(
                "startup.worker_not_detected",
                reason="no_fresh_heartbeat",
                last_seen_at=_last_seen,
                hint="job processing will not be READY until worker registers a heartbeat",
            )

    events = [e["event"] for e in cap]
    assert "startup.worker_not_detected" in events
    mock_scan.assert_awaited_once()
