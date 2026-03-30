import base64
from binascii import Error as BinasciiError
from collections.abc import Sequence
from datetime import datetime

import structlog
from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Client, Project

logger = structlog.get_logger(__name__)
_LIKE_ESCAPE_CHAR = "\\"


def _decode_project_list_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        decoded = base64.b64decode(cursor.encode(), validate=True).decode()
        ts_str, cur_id = decoded.rsplit(":", 1)
        if not cur_id:
            raise ValueError("missing project id")
        return datetime.fromisoformat(ts_str), cur_id
    except (BinasciiError, UnicodeDecodeError, ValueError) as exc:
        logger.warning("projects.list.invalid_cursor", error=str(exc))
        return None


def _build_project_search_pattern(search: str) -> str:
    escaped = (
        search
        .replace(_LIKE_ESCAPE_CHAR, _LIKE_ESCAPE_CHAR * 2)
        .replace("%", _LIKE_ESCAPE_CHAR + "%")
        .replace("_", _LIKE_ESCAPE_CHAR + "_")
    )
    return f"%{escaped}%"


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
        normalized_search = search.strip() if search else None
        query: Select[tuple[Project]] = select(Project).options(
            selectinload(Project.photos),
            selectinload(Project.created_by_user),
        )

        if organization_id is not None:
            query = query.where(Project.organization_id == organization_id)

        if status:
            query = query.where(Project.status == status)

        if normalized_search:
            like_value = _build_project_search_pattern(normalized_search)
            query = query.where(
                or_(
                    Project.title.ilike(like_value, escape=_LIKE_ESCAPE_CHAR),
                    Project.description.ilike(like_value, escape=_LIKE_ESCAPE_CHAR),
                )
            )

        if cursor:
            decoded_cursor = _decode_project_list_cursor(cursor)
            if decoded_cursor is not None:
                cursor_ts, cur_id = decoded_cursor
                query = query.where(
                    or_(
                        Project.created_at < cursor_ts,
                        and_(Project.created_at == cursor_ts, Project.id < cur_id),
                    )
                )

        # Stable sort: created_at DESC, id DESC. Enables reliable cursor-based pagination
        # because created_at never changes (unlike updated_at).
        query = query.order_by(Project.created_at.desc(), Project.id.desc())

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
