import json
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectFinalProposal


class FinalProposalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_by_project_id(self, project_id: str) -> ProjectFinalProposal | None:
        result = await self.session.execute(
            select(ProjectFinalProposal)
            .where(ProjectFinalProposal.project_id == project_id)
            .order_by(ProjectFinalProposal.created_at.desc(), ProjectFinalProposal.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_for_project(self, *, project_id: str, payload: dict) -> ProjectFinalProposal:
        final_proposal = ProjectFinalProposal(
            id=f"fnp_{uuid4().hex[:10]}",
            project_id=project_id,
            draft_version=int(payload.get("draftVersion", 1)),
            status=str(payload.get("status", "ready_for_export")),
            currency=str(payload.get("currency", "CZK")),
            subject=payload.get("subject"),
            summary=payload.get("summary"),
            total_price=payload.get("totalPrice"),
            snapshot_json=json.dumps(payload, ensure_ascii=True),
        )
        self.session.add(final_proposal)
        await self.session.commit()
        await self.session.refresh(final_proposal)
        return final_proposal

    async def delete_by_id(self, proposal_id: str) -> None:
        await self.session.execute(delete(ProjectFinalProposal).where(ProjectFinalProposal.id == proposal_id))
        await self.session.commit()
