from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Response


@pytest.mark.asyncio
async def test_health_internal_exposes_retry_dlq_and_queue_depth_details():
    from app.api.routes.system import (
        _DatabaseJobSnapshot,
        _WorkerHeartbeatSnapshot,
        health_internal,
    )
    from app.schemas.auth import AuthUserRead

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                startup_checks={
                    "database": "ok",
                    "schema": "ok",
                    "storage": "ok",
                },
                job_queue=object(),
            )
        )
    )
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
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = AsyncMock()
    session_ctx.__aexit__.return_value = False
    session_ctx.__aenter__.return_value.execute = AsyncMock(
        side_effect=[
            AsyncMock(),
            SimpleNamespace(scalar_one_or_none=lambda: None),
        ]
    )

    with (
        patch("app.api.routes.system.AsyncSessionFactory", return_value=session_ctx),
        patch(
            "app.api.routes.system._query_job_counts",
            new=AsyncMock(
                return_value=_DatabaseJobSnapshot(
                    jobs_running=2,
                    jobs_queued=7,
                    retry_queued_jobs=3,
                    dead_letter_jobs=1,
                    max_running_age_seconds=14.2,
                    oldest_queued_age_seconds=22.4,
                )
            ),
        ),
        patch("app.api.routes.system.get_analysis_job_queue_counts", new=AsyncMock(return_value=(6, 2))),
        patch("app.api.routes.system._query_queue_operational_counts", new=AsyncMock(return_value=(4, 2, 1))),
        patch(
            "app.api.routes.system._get_worker_heartbeat_snapshot",
            new=AsyncMock(
                return_value=_WorkerHeartbeatSnapshot(
                    alive=True,
                    last_seen_at="2026-04-01T10:00:00+00:00",
                    alive_instances=1,
                    seen_instances=1,
                )
            ),
        ),
        patch(
            "app.api.routes.system._queue_runtime_details",
            return_value={
                "state": "degraded",
                "mode": "failover",
                "candidateCount": 2,
                "activeUrl": "redis://secondary:6379/0",
                "degraded": True,
                "lastError": "primary down",
                "lastFailoverAt": "2026-04-01T10:00:00+00:00",
            },
        ),
        patch("app.api.routes.system._queue_runtime_state", return_value="degraded"),
        patch("app.api.routes.system._storage_ready_cached", new=AsyncMock(return_value=True)),
    ):
        body = await health_internal(
            request=request,
            response=response,
            _=current_user,
        )

    assert response.status_code == 200
    assert body["jobs"]["retryQueued"] == 3
    assert body["jobs"]["deadLetter"] == 1
    assert body["jobs"]["oldestQueuedAgeSeconds"] == 22.4
    assert body["queue"]["state"] == "degraded"
    assert body["queue"]["mode"] == "failover"
    assert body["queue"]["depth"]["durable"] == 6
    assert body["queue"]["depth"]["processing"] == 2
    assert body["queue"]["depth"]["scheduledRetry"] == 4
    assert body["queue"]["depth"]["scheduledRetryDueNow"] == 2
    assert body["queue"]["depth"]["deadLetterActive"] == 1


@pytest.mark.asyncio
async def test_mock_provider_rehearsal_failure_markers_are_deterministic():
    from app.ai.providers.mock_vision_provider import MockVisionProvider

    provider = MockVisionProvider()

    with pytest.raises(RuntimeError, match="persistent failure"):
        await provider.analyze_project(
            project={
                "description": "Case [rehearsal:fail-always]",
                "attemptCount": 1,
            },
            photos=[],
        )

    with pytest.raises(RuntimeError, match="retryable failure"):
        await provider.analyze_project(
            project={
                "description": "Case [rehearsal:fail-until-attempt=2]",
                "attemptCount": 2,
            },
            photos=[],
        )

    result = await provider.analyze_project(
        project={
            "description": "Case [rehearsal:fail-until-attempt=2]",
            "attemptCount": 3,
            "address_label": "Brno",
        },
        photos=[],
    )

    assert result["providerKey"] == "mock"
