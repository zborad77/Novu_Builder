"""FastAPI DI providery modulu cases."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cases.models import Project
from app.modules.cases.repository import ProjectRepository
from app.platform.db.session import get_db_session


class CaseReader:
    """Čtení zakázky pro routy ostatních modulů (existence + tenant guard přes org_id).

    Stejné dotazy jako dřívější ProjectService.get_project / get_project_lean.
    """

    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    async def get_project(self, project_id: str, *, organization_id: str | None = None) -> Project | None:
        return await self.repository.get_project(project_id, organization_id=organization_id)

    async def get_project_lean(self, project_id: str, *, organization_id: str | None = None) -> Project | None:
        return await self.repository.get_project_lean(project_id, organization_id=organization_id)


def get_case_reader(session: AsyncSession = Depends(get_db_session)) -> CaseReader:
    return CaseReader(ProjectRepository(session))
