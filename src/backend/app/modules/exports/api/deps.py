"""FastAPI DI providery modulu exports."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.http.deps import get_job_queue
from app.platform.db.session import get_db_session
from app.modules.exports.export_repository import ExportRepository
from app.modules.exports.storage_consistency_repository import StorageConsistencyRepository
from app.modules.exports.export_service import ExportService
from app.modules.exports.storage_consistency_service import StorageConsistencyService


def get_export_service(
    session: AsyncSession = Depends(get_db_session),
    work_queue=Depends(get_job_queue),
) -> ExportService:
    return ExportService(ExportRepository(session), work_queue=work_queue)


def get_storage_consistency_service(
    session: AsyncSession = Depends(get_db_session),
) -> StorageConsistencyService:
    return StorageConsistencyService(StorageConsistencyRepository(session))
