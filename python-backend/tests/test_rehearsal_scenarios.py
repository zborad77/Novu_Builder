from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.case_orchestration.quote_recalculation import (
    QuoteRecalculationCommandService,
    RequestQuoteRecalculationCommand,
)
from app.main import app as fastapi_app
from app.models import AnalysisJob, Project, ProjectExport
from app.repositories.analysis_repository import ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION
from app.services.analysis_service import AnalysisJobCreateResult, AnalysisService
from tests.conftest import _InMemoryAuthRedis


def _make_runtime(*, worker_heavy_concurrency: int = 1):
    from app.worker import runner as runner_module

    settings = MagicMock()
    settings.analysis_queue_max_depth = 100
    settings.heavy_queue_max_depth = 100
    settings.effective_backpressure_max_queued_jobs = 200

    return runner_module.WorkerRuntime(
        settings=settings,
        redis=AsyncMock(),
        redis_url="redis://localhost:6379/0",
        worker_instance_id="worker-rehearsal",
        heartbeat_key="worker:heartbeat:worker-rehearsal",
        job_executor=MagicMock(execute_lease=AsyncMock()),
        heavy_job_executor=MagicMock(execute_lease=AsyncMock()),
        worker_concurrency=1,
        job_lease_timeout_seconds=600,
        lease_reap_interval_seconds=30,
        concurrency_limiter=asyncio.Semaphore(1),
        inflight_tasks=set(),
        worker_heavy_concurrency=worker_heavy_concurrency,
        heavy_job_lease_timeout_seconds=1800,
        heavy_lease_reap_interval_seconds=30,
        heavy_concurrency_limiter=asyncio.Semaphore(max(1, worker_heavy_concurrency)),
        inflight_heavy_tasks=set(),
        last_heartbeat=time.monotonic(),
        last_lease_reap=0.0,
        last_heavy_lease_reap=0.0,
    )


async def _seed_project(db_session, test_tenants, *, status: str = "draft") -> str:
    token = uuid4().hex[:8]
    now = datetime.now(UTC)
    project_id = f"prj_rehearsal_{token}"
    db_session.add(
        Project(
            id=project_id,
            organization_id=test_tenants["org_a"],
            created_by_user_id="usr_e2e_a1",
            title=f"Rehearsal {token}",
            description="",
            status=status,
            source="mobile",
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.commit()
    return project_id


def _empty_analysis_snapshot():
    return MagicMock(
        has_any_entry=MagicMock(return_value=False),
        get_processing_lease=MagicMock(return_value=None),
        queued_job_ids=MagicMock(return_value=frozenset()),
        processing_job_ids=MagicMock(return_value=frozenset()),
        scheduled_retry_job_ids=MagicMock(return_value=frozenset()),
        dlq_job_ids=frozenset(),
    )


@pytest.mark.asyncio
async def test_worker_restart_recovers_analysis_job(db_session, test_tenants):
    from app.worker import runner

    await db_session.execute(delete(AnalysisJob))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants, status="analyzing")
    job = AnalysisJob(
        id=f"job_restart_{uuid4().hex[:8]}",
        project_id=project_id,
        status="running",
        job_type="manual_trigger",
        requested_by_user_id="usr_e2e_a1",
        lease_token="lease-restart-1",
        worker_id="worker-dead",
        started_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(job)
    await db_session.commit()

    runtime = _make_runtime()
    enqueue_mock = AsyncMock()
    service = MagicMock()
    service._job_running_is_stale = MagicMock(return_value=False)

    with (
        patch("app.worker.runner.inspect_analysis_job_transport", new=AsyncMock(return_value=_empty_analysis_snapshot())),
        patch("app.worker.runner.purge_analysis_job_transport", new=AsyncMock()),
        patch("app.worker.runner.enqueue_analysis_job", new=enqueue_mock),
        patch("app.worker.runner._build_worker_analysis_service", return_value=service),
        patch("app.worker.runner.is_worker_instance_alive", new=AsyncMock(return_value=False)),
    ):
        await runner._reconcile_startup_analysis_jobs(runtime)

    await db_session.refresh(job)
    assert job.status == "queued"
    enqueue_mock.assert_awaited_once()
    assert enqueue_mock.await_args.kwargs["job_id"] == job.id


@pytest.mark.asyncio
async def test_redis_flush_does_not_lose_jobs(db_session, test_tenants):
    from app.worker import runner

    await db_session.execute(delete(AnalysisJob))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants, status="intake")
    job = AnalysisJob(
        id=f"job_flush_{uuid4().hex[:8]}",
        project_id=project_id,
        status="queued",
        job_type="manual_trigger",
        requested_by_user_id="usr_e2e_a1",
    )
    db_session.add(job)
    await db_session.commit()

    runtime = _make_runtime()
    enqueue_mock = AsyncMock()

    with (
        patch("app.worker.runner.inspect_analysis_job_transport", new=AsyncMock(return_value=_empty_analysis_snapshot())),
        patch("app.worker.runner.enqueue_analysis_job", new=enqueue_mock),
        patch("app.worker.runner._build_worker_analysis_service", return_value=MagicMock()),
    ):
        await runner._reconcile_startup_analysis_jobs(runtime)

    await db_session.refresh(job)
    assert job.status == "queued"
    enqueue_mock.assert_awaited_once()
    assert enqueue_mock.await_args.kwargs["project_id"] == project_id


@pytest.mark.asyncio
async def test_duplicate_command_is_idempotent(db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants, status="quote_ready")

    project_repository = MagicMock()
    project_repository.get_project_lean = AsyncMock(
        return_value=SimpleNamespace(id=project_id, status="quote_ready")
    )

    quote_variant_service = MagicMock()
    quote_variant_service.can_recalculate_quote_variants = AsyncMock(return_value=True)

    analysis_service = AnalysisService(
        repository=AsyncMock(),
        photo_repository=AsyncMock(),
        provider_key="mock",
    )
    analysis_service.enqueue_existing_job_transport = AsyncMock(
        side_effect=lambda job, **_kwargs: AnalysisJobCreateResult(job=job, created_new=True)
    )

    command_service = QuoteRecalculationCommandService(
        project_repository=project_repository,
        quote_variant_service=quote_variant_service,
        analysis_service=analysis_service,
        job_queue=AsyncMock(),
    )
    command = RequestQuoteRecalculationCommand(
        case_id=project_id,
        organization_id=test_tenants["org_a"],
        requested_by_user_id="usr_e2e_a1",
        is_superadmin_context=False,
    )

    first = await command_service.handle(command)
    second = await command_service.handle(command)

    active_jobs = await db_session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.project_id == project_id,
            AnalysisJob.job_type == ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION,
            AnalysisJob.status.in_(("queued", "running")),
        )
    )

    assert first is not None
    assert second is not None
    assert first.job.id == second.job.id
    assert second.created_new is False
    assert active_jobs == 1


def test_reconnect_restores_consistent_state(test_tenants):
    original_auth_store = getattr(fastapi_app.state, "auth_token_store", None)
    fastapi_app.state.auth_token_store = _InMemoryAuthRedis()

    try:
        with TestClient(fastapi_app) as client:
            login_response = client.post(
                "/api/v1/auth/login",
                json=test_tenants["user_a"],
            )
            assert login_response.status_code == 200, login_response.text
            token = login_response.json()["accessToken"]
            auth_headers = {"Authorization": f"Bearer {token}"}

            create_case_response = client.post(
                "/api/v1/cases",
                json={"title": "Reconnect rehearsal case"},
                headers=auth_headers,
            )
            assert create_case_response.status_code == 201, create_case_response.text
            case_id = create_case_response.json()["id"]

            create_job_response = client.post(
                f"/api/v1/cases/{case_id}/analysis-jobs",
                headers=auth_headers,
            )
            assert create_job_response.status_code == 202, create_job_response.text
            job_id = create_job_response.json()["jobId"]

            with client.websocket_connect(f"/api/v1/ws/case-activity?token={token}") as websocket:
                websocket.send_json(
                    {
                        "type": "subscribe",
                        "caseId": case_id,
                        "jobId": job_id,
                    }
                )
                event = websocket.receive_json()
                assert event["caseId"] == case_id
                assert event["jobId"] == job_id

            detail_response = client.get(f"/api/v1/cases/{case_id}", headers=auth_headers)

        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["id"] == case_id
    finally:
        fastapi_app.state.auth_token_store = original_auth_store


@pytest.mark.asyncio
async def test_stuck_export_recovery(db_session, test_tenants):
    from app.worker import runner

    await db_session.execute(delete(ProjectExport))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants, status="sent")
    now = datetime.now(UTC)
    export = ProjectExport(
        id=f"exp_rehearsal_{uuid4().hex[:8]}",
        project_id=project_id,
        export_type="quote-pdf",
        status="pending",
        file_name="stuck-export.pdf",
        storage_key=None,
        created_at=now,
        completed_at=None,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(export)
    await db_session.commit()

    runtime = _make_runtime(worker_heavy_concurrency=1)
    enqueue_mock = AsyncMock()
    heavy_snapshot = MagicMock()
    heavy_snapshot.has_export = MagicMock(return_value=False)

    with (
        patch("app.worker.runner.inspect_heavy_job_transport", new=AsyncMock(return_value=heavy_snapshot)),
        patch("app.worker.runner.enqueue_heavy_job", new=enqueue_mock),
    ):
        await runner._reconcile_startup_exports(runtime)

    enqueue_mock.assert_awaited_once()
    assert enqueue_mock.await_args.kwargs["export_id"] == export.id
    assert enqueue_mock.await_args.kwargs["job_type"] == "export_generate"
