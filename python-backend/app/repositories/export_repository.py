from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectExport


@dataclass(frozen=True)
class ExpiredExportReference:
    export_id: str
    organization_id: str
    project_id: str
    storage_key: str | None
    expires_at: datetime


class ExportRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        export_id: str,
        project_id: str,
        export_type: str,
        status: str,
        file_name: str,
        storage_key: str | None,
        created_at: datetime,
        completed_at: datetime | None,
        expires_at: datetime,
    ) -> ProjectExport:
        export = ProjectExport(
            id=export_id,
            project_id=project_id,
            export_type=export_type,
            status=status,
            file_name=file_name,
            storage_key=storage_key,
            created_at=created_at,
            completed_at=completed_at,
            expires_at=expires_at,
        )
        self.session.add(export)
        await self.session.commit()
        await self.session.refresh(export)
        return export

    async def get_by_id(self, export_id: str) -> ProjectExport | None:
        return await self.session.get(ProjectExport, export_id)

    async def update_state(
        self,
        export: ProjectExport,
        *,
        status: str,
        storage_key: str | None,
        completed_at: datetime | None,
    ) -> ProjectExport:
        allowed_transitions = {
            "pending": {"pending", "generating", "failed"},
            "generating": {"generating", "completed", "failed"},
            "completed": {"completed", "failed"},
            "failed": {"failed"},
        }
        current_status = export.status
        if status not in allowed_transitions.get(current_status, set()):
            raise ValueError(f"Invalid export status transition: {current_status!r} -> {status!r}")
        if status == "completed":
            if not storage_key:
                raise ValueError("Completed export must have a storage_key.")
            if completed_at is None:
                raise ValueError("Completed export must have completed_at.")
        else:
            completed_at = None
            if status != "completed":
                storage_key = None
        export.status = status
        export.storage_key = storage_key
        export.completed_at = completed_at
        await self.session.commit()
        await self.session.refresh(export)
        return export

    async def list_expired(self, *, now: datetime | None = None) -> list[ExpiredExportReference]:
        current_time = now or datetime.now(UTC)
        result = await self.session.execute(
            select(
                ProjectExport.id,
                Project.organization_id,
                ProjectExport.project_id,
                ProjectExport.storage_key,
                ProjectExport.expires_at,
            )
            .join(Project, Project.id == ProjectExport.project_id)
            .where(
                ProjectExport.expires_at <= current_time,
                ProjectExport.status.in_(("completed", "failed")),
            )
            .order_by(ProjectExport.expires_at.asc(), ProjectExport.id.asc())
        )
        return [
            ExpiredExportReference(
                export_id=export_id,
                organization_id=organization_id,
                project_id=project_id,
                storage_key=storage_key,
                expires_at=expires_at,
            )
            for export_id, organization_id, project_id, storage_key, expires_at in result.all()
        ]

    async def list_incomplete(self) -> list[ProjectExport]:
        result = await self.session.execute(
            select(ProjectExport)
            .where(ProjectExport.status.in_(("pending", "generating")))
            .order_by(ProjectExport.created_at.asc(), ProjectExport.id.asc())
        )
        return list(result.scalars().all())

    async def delete_by_ids(self, export_ids: list[str]) -> int:
        if not export_ids:
            return 0
        result = await self.session.execute(
            delete(ProjectExport).where(ProjectExport.id.in_(export_ids))
        )
        await self.session.commit()
        return result.rowcount or 0
