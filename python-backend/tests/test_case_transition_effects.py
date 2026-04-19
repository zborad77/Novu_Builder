from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.case_workflow.case_actions import CaseActionService
from app.models import AnalysisJob, Project, ProjectExport, ProjectFinalProposal
from app.repositories.project_repository import ProjectRepository


_ORG_ID = "org_e2e_a"
_USER_ID = "usr_e2e_a1"


async def _create_project(db_session, *, project_id: str, status: str) -> Project:
    project = Project(
        id=project_id,
        organization_id=_ORG_ID,
        created_by_user_id=_USER_ID,
        title=f"Case {project_id}",
        status=status,
    )
    db_session.add(project)
    await db_session.commit()
    return project


def _service(db_session, *, work_queue=object()) -> CaseActionService:
    return CaseActionService(ProjectRepository(db_session), work_queue=work_queue)


@pytest.mark.asyncio
async def test_start_analysis_creates_job_and_enqueues_transport(db_session):
    project = await _create_project(db_session, project_id="prj_transition_analysis", status="intake")
    service = _service(db_session)

    with patch(
        "app.case_workflow.action_effects.enqueue_analysis_job",
        new=AsyncMock(),
    ) as enqueue_job:
        detail = await service.start_analysis(
            project.id,
            organization_id=_ORG_ID,
            actor_user_id=_USER_ID,
            actor_role="manager",
        )

    assert detail is not None
    assert detail.status == "analyzing"

    jobs = (
        await db_session.execute(
            select(AnalysisJob).where(AnalysisJob.project_id == project.id)
        )
    ).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == "queued"
    assert jobs[0].job_type == "manual_trigger"

    enqueue_job.assert_awaited_once()
    _, kwargs = enqueue_job.await_args
    assert kwargs["job_id"] == jobs[0].id
    assert kwargs["project_id"] == project.id
    assert kwargs["organization_id"] == _ORG_ID
    assert kwargs["is_superadmin_context"] is False


@pytest.mark.asyncio
async def test_approve_proposal_locks_pricing_snapshots(db_session):
    project = await _create_project(db_session, project_id="prj_transition_approve", status="proposal_ready")
    db_session.add_all(
        [
            ProjectFinalProposal(
                id="fp_transition_1",
                project_id=project.id,
                draft_version=1,
                status="ready_for_export",
                snapshot_json="{}",
            ),
            ProjectFinalProposal(
                id="fp_transition_2",
                project_id=project.id,
                draft_version=2,
                status="ready_for_export",
                snapshot_json="{}",
            ),
        ]
    )
    await db_session.commit()

    detail = await _service(db_session).approve_proposal(
        project.id,
        organization_id=_ORG_ID,
        actor_user_id=_USER_ID,
        actor_role="manager",
    )

    assert detail is not None
    assert detail.status == "quote_ready"

    proposals = (
        await db_session.execute(
            select(ProjectFinalProposal).where(ProjectFinalProposal.project_id == project.id)
        )
    ).scalars().all()
    assert {proposal.status for proposal in proposals} == {"approved"}


@pytest.mark.asyncio
async def test_send_quote_creates_supported_export_and_enqueues_heavy_job(db_session):
    project = await _create_project(db_session, project_id="prj_transition_send", status="quote_ready")
    db_session.add(
        ProjectFinalProposal(
            id="fp_transition_send",
            project_id=project.id,
            draft_version=1,
            status="approved",
            snapshot_json="{}",
        )
    )
    await db_session.commit()

    with patch(
        "app.case_workflow.action_effects.enqueue_heavy_job",
        new=AsyncMock(),
    ) as enqueue_heavy:
        detail = await _service(db_session).send_quote(
            project.id,
            organization_id=_ORG_ID,
            actor_user_id=_USER_ID,
            actor_role="manager",
        )

    assert detail is not None
    assert detail.status == "sent"

    exports = (
        await db_session.execute(
            select(ProjectExport).where(ProjectExport.project_id == project.id)
        )
    ).scalars().all()
    assert len(exports) == 1
    assert exports[0].export_type == "quote-pdf"
    assert exports[0].status == "pending"
    assert exports[0].file_name.endswith(".pdf")

    enqueue_heavy.assert_awaited_once()
    _, kwargs = enqueue_heavy.await_args
    assert kwargs["job_type"] == "export_generate"
    assert kwargs["project_id"] == project.id
    assert kwargs["organization_id"] == _ORG_ID
    assert kwargs["export_id"] == exports[0].id


@pytest.mark.asyncio
async def test_complete_creates_case_zip_export_and_enqueues_heavy_job(db_session):
    project = await _create_project(db_session, project_id="prj_transition_complete", status="sent")

    with patch(
        "app.case_workflow.action_effects.enqueue_heavy_job",
        new=AsyncMock(),
    ) as enqueue_heavy:
        detail = await _service(db_session).complete(
            project.id,
            organization_id=_ORG_ID,
            actor_user_id=_USER_ID,
            actor_role="manager",
        )

    assert detail is not None
    assert detail.status == "archived"

    exports = (
        await db_session.execute(
            select(ProjectExport).where(ProjectExport.project_id == project.id)
        )
    ).scalars().all()
    assert len(exports) == 1
    assert exports[0].export_type == "case-zip"
    assert exports[0].status == "pending"
    assert exports[0].file_name.endswith(".zip")

    enqueue_heavy.assert_awaited_once()
    _, kwargs = enqueue_heavy.await_args
    assert kwargs["job_type"] == "export_generate"
    assert kwargs["project_id"] == project.id
    assert kwargs["organization_id"] == _ORG_ID
    assert kwargs["export_id"] == exports[0].id
