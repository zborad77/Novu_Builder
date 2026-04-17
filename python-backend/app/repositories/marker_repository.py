from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Marker


class MarkerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        case_id: str,
        image_id: str | None,
        marker_type: str,
        marker_source: str = "user",
        x: float,
        y: float,
        width: float | None,
        height: float | None,
        label: str,
        severity: str | None,
        created_by: str | None,
    ) -> Marker:
        marker = Marker(
            id=f"mrk_{uuid4().hex[:10]}",
            case_id=case_id,
            image_id=image_id,
            marker_type=marker_type,
            marker_source=marker_source,
            x=x,
            y=y,
            width=width,
            height=height,
            label=label,
            severity=severity,
            created_by=created_by,
        )
        self.session.add(marker)
        await self.session.flush()
        return marker

    async def list_by_case(self, case_id: str) -> Sequence[Marker]:
        result = await self.session.execute(
            select(Marker)
            .where(Marker.case_id == case_id)
            .order_by(Marker.created_at.asc())
        )
        return result.scalars().all()

    async def list_by_image(self, image_id: str) -> Sequence[Marker]:
        result = await self.session.execute(
            select(Marker)
            .where(Marker.image_id == image_id)
            .order_by(Marker.created_at.asc())
        )
        return result.scalars().all()

    async def get_by_id(self, marker_id: str) -> Marker | None:
        result = await self.session.execute(
            select(Marker).where(Marker.id == marker_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_id(self, marker_id: str) -> bool:
        result = await self.session.execute(
            delete(Marker).where(Marker.id == marker_id)
        )
        return result.rowcount > 0
