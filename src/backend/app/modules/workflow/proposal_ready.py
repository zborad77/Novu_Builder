"""Implementace portu analysis.ProposalReadyNotifier: analyzing -> proposal_ready po rekalkulaci."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.repository import ProjectRepository
from app.modules.workflow.case_actions import CaseActionService


async def mark_proposal_ready(session: AsyncSession, project_id: str, reason: str) -> None:
    await CaseActionService(ProjectRepository(session)).worker_proposal_ready(project_id, reason=reason)
