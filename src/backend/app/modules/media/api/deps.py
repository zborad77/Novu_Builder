"""FastAPI DI providery modulu media."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_job_queue
from app.platform.db.session import get_db_session
from app.modules.media.photo_repository import PhotoRepository
from app.modules.media.photo_service import PhotoService


def get_photo_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> PhotoService:
    repository = PhotoRepository(session)
    return PhotoService(repository, work_queue=work_queue)
