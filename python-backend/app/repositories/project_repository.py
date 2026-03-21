from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Client, Project


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_projects(self, *, status: str | None = None, search: str | None = None) -> Sequence[Project]:
        query: Select[tuple[Project]] = (
            select(Project)
            .options(selectinload(Project.photos), selectinload(Project.proposal_draft), selectinload(Project.final_proposals), selectinload(Project.created_by_user))
            .order_by(Project.updated_at.desc(), Project.created_at.desc())
        )

        if status:
            query = query.where(Project.status == status)

        if search:
            like_value = f"%{search.lower()}%"
            query = query.where(
                (Project.title.ilike(like_value)) | (Project.description.ilike(like_value))
            )

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_project(self, project_id: str) -> Project | None:
        from app.models import AnalysisResult, QuoteVariant, QuoteItem
        from sqlalchemy.orm import selectinload as sil
        result = await self.session.execute(
            select(Project)
            .options(
                selectinload(Project.client),
                selectinload(Project.photos),
                selectinload(Project.proposal_draft),
                selectinload(Project.final_proposals),
                selectinload(Project.analysis_results),
                selectinload(Project.quote_variants).selectinload(QuoteVariant.items),
            )
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def create_project(
        self,
        *,
        project_id: str,
        organization_id: str,
        created_by_user_id: str,
        title: str,
        description: str | None,
        client_id: str | None,
        property_type: str | None,
        repair_scope: str | None,
        location_lat: float | None,
        location_lng: float | None,
        address_label: str | None,
        source: str = "mobile",
    ) -> Project:
        project = Project(
            id=project_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
            client_id=client_id,
            title=title,
            description=description,
            status="draft",
            source=source,
            property_type=property_type,
            repair_scope=repair_scope,
            location_lat=location_lat,
            location_lng=location_lng,
            address_label=address_label,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return await self.get_project(project.id)  # type: ignore[return-value]

    async def update_project(self, project: Project, changes: dict) -> Project:
        for key, value in changes.items():
            setattr(project, key, value)

        await self.session.commit()
        await self.session.refresh(project)
        return await self.get_project(project.id)  # type: ignore[return-value]

    async def get_client(self, client_id: str | None) -> Client | None:
        if not client_id:
            return None
        result = await self.session.execute(select(Client).where(Client.id == client_id))
        return result.scalar_one_or_none()
