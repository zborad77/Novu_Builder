"""FastAPI DI providery modulu workflow."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_job_queue
from app.platform.db.session import get_db_session
from app.modules.workflow.case_actions import CaseActionService
from app.modules.quoting.final_proposal_repository import FinalProposalRepository
from app.modules.cases.repository import ProjectRepository
from app.modules.quoting.proposal_draft_repository import ProposalDraftRepository
from app.modules.workflow.ports import final_proposal_exporter
from app.modules.workflow.project_service import ProjectService


def get_project_service(session: AsyncSession = Depends(get_db_session)) -> ProjectService:
    return ProjectService(
        ProjectRepository(session),
        ProposalDraftRepository(session),
        FinalProposalRepository(session),
        final_proposal_exporter(session),
    )


def get_case_action_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> CaseActionService:
    return CaseActionService(ProjectRepository(session), work_queue=work_queue)
