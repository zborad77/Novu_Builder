import base64
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Client, Project


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_projects(
        self,
        *,
        organization_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 200,
        cursor: str | None = None,
    ) -> Sequence[Project]:
        # Stable sort: created_at DESC, id DESC. Enables reliable cursor-based pagination
        # because created_at never changes (unlike updated_at).
        query: Select[tuple[Project]] = (
            select(Project)
            .options(selectinload(Project.photos), selectinload(Project.created_by_user))
            .order_by(Project.created_at.desc(), Project.id.desc())
        )

        if organization_id:
            query = query.where(Project.organization_id == organization_id)

        if status:
            query = query.where(Project.status == status)

        if search:
            like_value = f"%{search.lower()}%"
            query = query.where(
                (Project.title.ilike(like_value)) | (Project.description.ilike(like_value))
            )

        if cursor:
            try:
                decoded = base64.b64decode(cursor.encode()).decode()
                ts_str, cur_id = decoded.rsplit(":", 1)
                cursor_ts = datetime.fromisoformat(ts_str)
                query = query.where(
                    or_(
                        Project.created_at < cursor_ts,
                        and_(Project.created_at == cursor_ts, Project.id < cur_id),
                    )
                )
            except Exception:
                pass  # invalid cursor → return from start

        # Fetch limit+1 to detect whether a next page exists
        query = query.limit(limit + 1)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_project_lean(self, project_id: str, *, organization_id: str | None = None) -> Project | None:
        """Fetch only the Project row (no selectinload).

        Use when the caller only needs to verify existence/org membership or
        pass the ORM object to update_project() (which re-fetches with full
        graph internally).  Saves 5 extra SELECT queries compared to
        get_project().
        """
        query = select(Project).where(Project.id == project_id)
        if organization_id is not None:
            query = query.where(Project.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_project(self, project_id: str, *, organization_id: str | None = None) -> Project | None:
        # HEAVY FETCH: loads client, photos, proposal_draft, final_proposals,
        # analysis_results, and quote_variants (with items) in separate SELECT
        # queries via selectinload. Use get_project_lean() instead when the
        # caller only needs existence/org guard or will mutate via
        # update_project() (which re-fetches with full graph internally).
        # Known remaining over-fetches: mark_project_sent (needs final_proposals
        # only), update_proposal_draft (uses full graph in build_project_detail).
        from app.models import QuoteVariant
        query = (
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
        if organization_id is not None:
            query = query.where(Project.organization_id == organization_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def client_belongs_to_org(self, client_id: str, organization_id: str) -> bool:
        """Return True if the client exists and belongs to the given org."""
        result = await self.session.execute(
            select(Client.id).where(Client.id == client_id, Client.organization_id == organization_id)
        )
        return result.scalar_one_or_none() is not None

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
