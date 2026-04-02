from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.worker.queue import LeasedAnalysisJob


def _analysis_lease(
    *,
    job_id: str = "job_resilience_1",
    project_id: str = "proj_resilience_1",
    organization_id: str = "org_e2e_a",
    worker_id: str = "worker-resilience",
    token: str = "lease-resilience-1",
) -> LeasedAnalysisJob:
    return LeasedAnalysisJob(
        token=token,
        payload={
            "job_id": job_id,
            "project_id": project_id,
            "organization_id": organization_id,
            "is_superadmin_context": False,
        },
        raw_payload="{}",
        worker_id=worker_id,
        leased_at_ms=1_700_000_000_000,
        lease_timeout_ms=60_000,
        expires_at_ms=1_700_000_060_000,
    )


def _make_runtime():
    from app.worker import runner as runner_module

    settings = MagicMock()
    settings.ai_analysis_provider = "mock"

    return runner_module.WorkerRuntime(
        settings=settings,
        redis=AsyncMock(),
        redis_url="redis://localhost:6379/0",
        worker_instance_id="worker-resilience",
        heartbeat_key="worker:heartbeat:worker-resilience",
        job_executor=MagicMock(execute_lease=AsyncMock()),
        heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
        worker_concurrency=1,
        job_lease_timeout_seconds=60,
        lease_reap_interval_seconds=5,
        concurrency_limiter=asyncio.Semaphore(1),
        inflight_tasks=set(),
        worker_heavy_concurrency=0,
        last_lease_reap=0.0,
    )


@pytest.fixture(autouse=True)
def _reset_runtime_caches():
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
    get_settings.cache_clear()


def _clear_readiness_caches_for(app) -> None:
    from app.api.routes.system import (
        _clear_operational_metrics_cache,
        _clear_readiness_db_cache,
        _clear_readiness_storage_cache,
    )

    _clear_readiness_db_cache(app)
    _clear_readiness_storage_cache(app)
    _clear_operational_metrics_cache(app)


@asynccontextmanager
async def _fresh_client():
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield app, client


async def _login(client: AsyncClient, *, email: str, password: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()


@dataclass(frozen=True)
class _WorkerSnapshot:
    alive: bool | None
    last_seen_at: str | None
    alive_instances: int | None
    seen_instances: int | None


@pytest.mark.asyncio
async def test_backend_restart_preserves_auth_flow_and_readiness(test_tenants):
    first_tokens: dict | None = None

    async with _fresh_client() as (_app, client):
        ready_before = await client.get("/api/v1/ready")
        assert ready_before.status_code == 200

        first_tokens = await _login(
            client,
            email=test_tenants["user_a"]["email"],
            password=test_tenants["user_a"]["password"],
        )
        me_before = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {first_tokens['accessToken']}"},
        )
        assert me_before.status_code == 200
        assert me_before.json()["organizationId"] == test_tenants["org_a"]

    assert first_tokens is not None

    async with _fresh_client() as (_app, client):
        ready_after = await client.get("/api/v1/ready")
        assert ready_after.status_code == 200

        refresh = await client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": first_tokens["refreshToken"]},
        )
        assert refresh.status_code == 200
        refreshed = refresh.json()

        me_after = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed['accessToken']}"},
        )
        assert me_after.status_code == 200
        assert me_after.json()["organizationId"] == test_tenants["org_a"]


@pytest.mark.asyncio
async def test_worker_restart_requeues_expired_job_lease_without_losing_job():
    from app.worker import runner

    runtime = _make_runtime()
    expired_lease = _analysis_lease()
    service = MagicMock(reconcile_expired_lease=AsyncMock(return_value="requeue"))
    requeue_mock = AsyncMock(return_value=True)
    metrics_mock = MagicMock()

    with (
        patch("app.worker.runner.get_expired_analysis_job_leases", new=AsyncMock(return_value=[expired_lease])),
        patch("app.worker.runner._build_worker_analysis_service", return_value=service),
        patch("app.worker.runner.requeue_expired_analysis_job", new=requeue_mock),
        patch("app.worker.runner.drop_expired_analysis_job", new=AsyncMock(return_value=False)),
        patch("app.worker.runner.record_reaper_requeues", new=metrics_mock),
    ):
        await runner._run_lease_reaper_if_due(runtime, now_monotonic=9999.0)

    service.reconcile_expired_lease.assert_awaited_once_with(expired_lease)
    requeue_mock.assert_awaited_once_with(runtime.redis, expired_lease)
    metrics_mock.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_redis_restart_transitions_processing_readiness_to_not_ready_then_recovers(app_client):
    from app.main import app as fastapi_app

    worker_snapshot = _WorkerSnapshot(
        alive=True,
        last_seen_at="2026-04-01T10:00:00+00:00",
        alive_instances=1,
        seen_instances=1,
    )
    original_job_queue = getattr(fastapi_app.state, "job_queue", None)
    fastapi_app.state.job_queue = object()
    try:
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(side_effect=OSError("redis down"))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            degraded = await app_client.get("/api/v1/ready/processing?strict=1")

        _clear_readiness_caches_for(fastapi_app)
        with (
            patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(0, 0))),
            patch("app.api.routes.system._get_worker_heartbeat_snapshot", new=AsyncMock(return_value=worker_snapshot)),
        ):
            recovered = await app_client.get("/api/v1/ready/processing?strict=1")
    finally:
        fastapi_app.state.job_queue = original_job_queue

    assert degraded.status_code == 503
    assert degraded.json()["jobProcessingReady"] is False
    assert degraded.json()["queueState"] == "unavailable"

    assert recovered.status_code == 200
    assert recovered.json()["jobProcessingReady"] is True
    assert recovered.json()["queueState"] == "ready"


@pytest.mark.asyncio
async def test_postgres_restart_flips_api_readiness_and_recovers(app_client):
    from app.main import app as fastapi_app

    failing_ctx = AsyncMock()
    failing_ctx.__aenter__.side_effect = RuntimeError("postgres unavailable")
    failing_ctx.__aexit__ = AsyncMock(return_value=False)

    degraded_ready = None
    degraded_health = None
    with patch("app.api.routes.system.AsyncSessionFactory", return_value=failing_ctx):
        degraded_health = await app_client.get("/api/v1/health")
        degraded_ready = await app_client.get("/api/v1/ready")

    _clear_readiness_caches_for(fastapi_app)
    recovered_ready = await app_client.get("/api/v1/ready")

    assert degraded_health is not None
    assert degraded_ready is not None
    assert degraded_health.status_code == 200
    assert degraded_ready.status_code == 503
    assert recovered_ready.status_code == 200


@pytest.mark.asyncio
async def test_storage_dependency_outage_keeps_health_alive_but_blocks_readiness_until_recovery(app_client):
    from app.main import app as fastapi_app

    degraded_health = None
    degraded_ready = None
    with patch("app.api.routes.system.verify_storage_health", new=AsyncMock(side_effect=RuntimeError("s3 timeout"))):
        degraded_health = await app_client.get("/api/v1/health")
        degraded_ready = await app_client.get("/api/v1/ready")

    _clear_readiness_caches_for(fastapi_app)
    recovered_ready = await app_client.get("/api/v1/ready")

    assert degraded_health is not None
    assert degraded_ready is not None
    assert degraded_health.status_code == 200
    assert degraded_ready.status_code == 503
    assert recovered_ready.status_code == 200
