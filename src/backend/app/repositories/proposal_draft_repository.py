from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectProposalDraft


class ProposalVersionConflictError(Exception):
    """Raised when expected_version does not match the stored draft version."""
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"Proposal draft version conflict: current version is {current_version}")


class ProposalDraftRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_project_id(self, project_id: str) -> ProjectProposalDraft | None:
        result = await self.session.execute(
            select(ProjectProposalDraft).where(ProjectProposalDraft.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def upsert_for_project(
        self,
        project_id: str,
        changes: dict,
        *,
        expected_version: int | None = None,
    ) -> ProjectProposalDraft:
        draft = await self.get_by_project_id(project_id)
        is_new = draft is None
        if draft is None:
            draft = ProjectProposalDraft(
                id=f"prd_{uuid4().hex[:10]}",
                project_id=project_id,
                version=1,
            )
            self.session.add(draft)
        elif expected_version is not None and draft.version != expected_version:
            raise ProposalVersionConflictError(current_version=draft.version)

        has_changes = False
        for key, value in changes.items():
            if getattr(draft, key) != value:
                setattr(draft, key, value)
                has_changes = True

        if not is_new and has_changes:
            draft.version += 1

        await self.session.commit()
        await self.session.refresh(draft)
        return draft
