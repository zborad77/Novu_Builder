from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from unittest.mock import AsyncMock, patch

from app.models import AnalysisJob, AnalysisResult, Organization, Project, User
from app.repositories.analysis_repository import ANALYSIS_JOB_STATUS_COMPLETED
from app.services.analysis_service import AnalysisService


@pytest.mark.asyncio
async def test_duplicate_execution_after_commit_and_requeue_is_idempotent(db_session):
    suffix = uuid4().hex[:8]
    org_id = f"org_dup_{suffix}"
    user_id = f"usr_dup_{suffix}"
    project_id = f"proj_dup_{suffix}"
    job_id = f"job_dup_{suffix}"

    db_session.add(
        Organization(
            id=org_id,
            name="Duplicate Guard Org",
            default_currency="CZK",
        )
    )
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            email=f"dup_{suffix}@test.local",
            password_hash="not-used-in-this-test",
            full_name="Duplicate Guard",
            role="manager",
            is_active=True,
            is_superadmin=False,
        )
    )
    db_session.add(
        Project(
            id=project_id,
            organization_id=org_id,
            created_by_user_id=user_id,
            title="Duplicate execution guard",
            status="draft",
            source="mobile",
        )
    )
    db_session.add(
        AnalysisJob(
            id=job_id,
            project_id=project_id,
            status="queued",
            job_type="manual_trigger",
            requested_by_user_id=user_id,
            retry_count=0,
        )
    )
    await db_session.commit()

    worker_factory = async_sessionmaker(
        bind=db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    service = AnalysisService(
        repository=AsyncMock(),
        photo_repository=AsyncMock(),
        provider_key="mock",
    )
    run_analysis = AsyncMock(
        return_value={
            "jobStatus": "completed",
            "estimatedAreaSqm": 12.5,
            "providerKey": "mock",
            "modelName": "mock-vision",
        }
    )

    with (
        patch("app.services.analysis_service.WorkerAsyncSessionFactory", worker_factory),
        patch("app.services.analysis_service.run_project_analysis", new=run_analysis),
    ):
        await service.execute_job(
            job_id,
            project_id,
            organization_id=org_id,
            lease_token="lease-1",
            worker_id="worker-a",
        )
        await service.execute_job(
            job_id,
            project_id,
            organization_id=org_id,
            lease_token="lease-2",
            worker_id="worker-b",
        )

    assert run_analysis.await_count == 1

    async with worker_factory() as session:
        stored_job = await session.get(AnalysisJob, job_id)
        stored_results = list(
            (
                await session.execute(
                    select(AnalysisResult).where(AnalysisResult.analysis_job_id == job_id)
                )
            ).scalars()
        )

    assert stored_job is not None
    assert stored_job.status == ANALYSIS_JOB_STATUS_COMPLETED
    assert stored_job.lease_token is None
    assert stored_job.worker_id is None
    assert len(stored_results) == 1
