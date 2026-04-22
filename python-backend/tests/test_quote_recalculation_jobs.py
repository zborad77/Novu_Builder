from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AnalysisJob, Project
from app.repositories.analysis_repository import (
    ANALYSIS_JOB_STATUS_COMPLETED,
    ANALYSIS_JOB_STATUS_QUEUED,
    ANALYSIS_JOB_TYPE_MANUAL_TRIGGER,
    ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION,
    AnalysisRepository,
)
from app.repositories.photo_repository import PhotoRepository
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.services.analysis_service import AnalysisService
from app.services.quote_variant_service import QuoteVariantRecalculationResult
from app.worker.queue import dequeue_analysis_job
from tests.test_r19_job_queue import FakeRedisQueue


async def _create_project(db_session, test_tenants, *, status: str = "draft") -> Project:
    project = Project(
        id=f"prj_quote_{uuid4().hex[:8]}",
        organization_id=test_tenants["org_a"],
        created_by_user_id="usr_e2e_a1",
        title="Quote job test",
        description="",
        status=status,
        source="mobile",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _create_analysis_job(
    db_session,
    project: Project,
    *,
    job_type: str,
    status: str = ANALYSIS_JOB_STATUS_QUEUED,
    requested_by_user_id: str | None = "usr_e2e_a1",
    parent_job_id: str | None = None,
) -> AnalysisJob:
    job = AnalysisJob(
        id=f"job_{uuid4().hex[:8]}",
        project_id=project.id,
        requested_by_user_id=requested_by_user_id,
        parent_job_id=parent_job_id,
        status=status,
        job_type=job_type,
        retry_count=0,
        attempt_count=0,
        created_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.commit()
    return job


@pytest.mark.asyncio
async def test_execute_analysis_job_enqueues_followup_quote_recalculation_job(db_session, test_tenants):
    project = await _create_project(db_session, test_tenants, status="analyzing")
    job = await _create_analysis_job(
        db_session,
        project,
        job_type=ANALYSIS_JOB_TYPE_MANUAL_TRIGGER,
    )
    redis = FakeRedisQueue()
    worker_factory = async_sessionmaker(
        bind=db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    service = AnalysisService(
        repository=AnalysisRepository(db_session),
        photo_repository=PhotoRepository(db_session),
        work_catalog_repository=WorkCatalogRepository(db_session),
        provider_key="mock",
    )

    analysis_payload = {
        "objectType": "roof",
        "surfaceCondition": "damaged",
        "recommendedScope": "repair",
        "estimatedAreaSqm": 12.5,
        "modelName": "mock-model",
        "modelVersion": "1",
        "referencePhotoId": None,
        "estimatedQuantity": 12.5,
        "estimatedUnit": "sqm",
        "materials": [],
        "workflowSteps": [],
    }

    with (
        patch("app.services.analysis_service.WorkerAsyncSessionFactory", worker_factory),
        patch("app.services.analysis_service.run_project_analysis", new=AsyncMock(return_value=analysis_payload)),
    ):
        result = await service.execute_job(
            job.id,
            project.id,
            project.organization_id,
            is_superadmin_context=False,
            job_queue=redis,
        )

    assert result.disposition == "completed"

    await db_session.refresh(job)
    assert job.status == ANALYSIS_JOB_STATUS_COMPLETED

    follow_up_job = (
        await db_session.execute(
            select(AnalysisJob).where(
                AnalysisJob.parent_job_id == job.id,
                AnalysisJob.job_type == ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION,
            )
        )
    ).scalar_one()
    assert follow_up_job is not None
    assert follow_up_job.status == ANALYSIS_JOB_STATUS_QUEUED

    lease = await dequeue_analysis_job(redis, worker_id="worker-a", lease_timeout_seconds=600)
    assert lease is not None
    assert lease.job_id == follow_up_job.id
    assert lease.project_id == project.id


@pytest.mark.asyncio
async def test_execute_quote_recalculation_job_completes_without_analysis_result(db_session, test_tenants):
    project = await _create_project(db_session, test_tenants)
    job = await _create_analysis_job(
        db_session,
        project,
        job_type=ANALYSIS_JOB_TYPE_QUOTE_RECALCULATION,
    )
    worker_factory = async_sessionmaker(
        bind=db_session.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    service = AnalysisService(
        repository=AnalysisRepository(db_session),
        photo_repository=PhotoRepository(db_session),
        work_catalog_repository=WorkCatalogRepository(db_session),
        provider_key="mock",
    )

    quote_result = QuoteVariantRecalculationResult(
        variants=[],
        source="project_work_items",
    )

    with (
        patch("app.services.analysis_service.WorkerAsyncSessionFactory", worker_factory),
        patch(
            "app.services.quote_variant_service.QuoteVariantService.recalculate_quote_variants_with_context",
            new=AsyncMock(return_value=quote_result),
        ),
    ):
        result = await service.execute_job(
            job.id,
            project.id,
            project.organization_id,
            is_superadmin_context=False,
            job_queue=FakeRedisQueue(),
        )

    assert result.disposition == "completed"
    await db_session.refresh(job)
    assert job.status == ANALYSIS_JOB_STATUS_COMPLETED
    assert job.output_summary is not None
    assert '"job_type": "quote_recalculation"' in job.output_summary
    assert '"variant_count": 0' in job.output_summary
