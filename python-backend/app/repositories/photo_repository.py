from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProjectPhoto


class PhotoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_photos_by_project_id(self, project_id: str) -> Sequence[ProjectPhoto]:
        result = await self.session.execute(
            select(ProjectPhoto)
            .where(ProjectPhoto.project_id == project_id)
            .order_by(ProjectPhoto.sort_order.asc(), ProjectPhoto.created_at.asc())
        )
        return result.scalars().all()

    async def count_photos(self, project_id: str) -> int:
        result = await self.session.execute(
            select(func.count(ProjectPhoto.id)).where(ProjectPhoto.project_id == project_id)
        )
        return int(result.scalar_one())

    async def get_next_sort_order(self, project_id: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(ProjectPhoto.sort_order), 0)).where(ProjectPhoto.project_id == project_id)
        )
        return int(result.scalar_one()) + 1

    async def get_photo(self, project_id: str, photo_id: str) -> ProjectPhoto | None:
        result = await self.session.execute(
            select(ProjectPhoto).where(
                ProjectPhoto.project_id == project_id,
                ProjectPhoto.id == photo_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_photo_by_id(self, photo_id: str) -> ProjectPhoto | None:
        result = await self.session.execute(
            select(ProjectPhoto).where(ProjectPhoto.id == photo_id)
        )
        return result.scalar_one_or_none()

    async def clear_primary(self, project_id: str) -> None:
        photos = await self.list_photos_by_project_id(project_id)
        for photo in photos:
            photo.is_primary = False

    async def clear_analysis_reference(self, project_id: str) -> None:
        photos = await self.list_photos_by_project_id(project_id)
        for photo in photos:
            photo.is_analysis_reference = False

    async def add_photo(self, photo: ProjectPhoto) -> ProjectPhoto:
        self.session.add(photo)
        await self.session.commit()
        await self.session.refresh(photo)
        return photo

    async def update_photo(self, photo: ProjectPhoto) -> ProjectPhoto:
        await self.session.commit()
        await self.session.refresh(photo)
        return photo

    async def save_changes(self) -> None:
        await self.session.commit()

    async def remove_photo(self, photo: ProjectPhoto) -> None:
        await self.session.delete(photo)
        await self.session.commit()
