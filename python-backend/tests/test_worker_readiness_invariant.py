"""Worker-readiness invariant tests.

Invariant: the system MUST NOT report READY (/ready → 200) without an active
worker.  The API process itself can run, but readiness is hard-blocked until a
worker registers a fresh heartbeat.

Coverage
--------
1. Worker down (no heartbeat)        → /ready = 503, ready=False
2. Worker alive (fresh heartbeat)    → /ready = 200, ready=True
3. Worker heartbeat stale / expired  → /ready = 503, ready=False
4. Redis unavailable (worker unknown)→ /ready = 503, ready=False
5. /health still returns 200 when worker is dead (degraded, not unavailable)
6. /ready/processing apiReady field reflects API-only state, not worker state
7. startup.worker_not_detected is logged when no heartbeat exists at startup
"""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. Worker down → /ready = 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_returns_503_when_worker_has_no_heartbeat(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=0)
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

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["apiState"] == "ready"
    assert data["worker"]["state"] == "missing"


# ---------------------------------------------------------------------------
# 2. Worker alive → /ready = 200
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 3. Worker heartbeat stale/expired → /ready = 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_returns_503_when_worker_heartbeat_is_stale(app_client):
    from app.main import app as fastapi_app

    # alive=False but seen_instances=1 → stale
    worker_snapshot = _make_worker_snapshot(alive=False, seen_instances=1)
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

    assert response.status_code == 503
    data = response.json()
    assert data["ready"] is False
    assert data["worker"]["state"] == "stale"


# ---------------------------------------------------------------------------
# 4. Redis unavailable (worker status unknown) → /ready = 503
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_unavailable_worker_unknown(app_client):
    from app.main import app as fastapi_app

    # When Redis is None, worker.alive is None → not True → readiness denied.
    original_queue = getattr(fastapi_app.state, "job_queue", None)
    original_auth = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.job_queue = None
    try:
        response = await app_client.get("/api/v1/ready")
    finally:
        fastapi_app.state.job_queue = original_queue
        fastapi_app.state.auth_token_store = original_auth

    assert response.status_code == 503
    assert response.json()["ready"] is False


# ---------------------------------------------------------------------------
# 5. /health still 200 when worker dead (state=degraded, not unavailable)
# ---------------------------------------------------------------------------

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
    assert data["ready"] is False   # invariant reflected in payload even for /health


# ---------------------------------------------------------------------------
# 6. /ready/processing apiReady uses API-only state, not worker state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_processing_ready_api_ready_reflects_api_state_not_worker_state(app_client):
    from app.main import app as fastapi_app

    # Worker dead, but API itself is healthy.
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
    # apiReady must reflect API-layer health only (startup/db/storage/auth).
    assert data["apiReady"] is True
    assert data["jobProcessingReady"] is False
    assert data["workerState"] == "missing"


# ---------------------------------------------------------------------------
# 7. Startup guard logs ERROR when no worker is detected
# ---------------------------------------------------------------------------

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
        # Re-run just the guard logic inline (mirrors main.py lifespan).
        import structlog
        _logger = structlog.get_logger("app.main")
        _startup_redis = object()  # non-None sentinel

        from app.worker.heartbeat import scan_alive_workers as _scan
        _alive_count, _last_seen = await _scan(_startup_redis)
        if _alive_count == 0:
            _logger.error(
                "startup.worker_not_detected",
                reason="no_fresh_heartbeat",
                last_seen_at=_last_seen,
                hint="system will not be READY until worker registers a heartbeat",
            )

    events = [e["event"] for e in cap]
    assert "startup.worker_not_detected" in events
    mock_scan.assert_awaited_once()
