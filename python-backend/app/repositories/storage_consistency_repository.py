from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectExport, ProjectPhoto


@dataclass(frozen=True)
class PhotoStorageReference:
    organization_id: str
    project_id: str
    photo_id: str
    storage_key: str
    variant: str


@dataclass(frozen=True)
class ExportStorageReference:
    organization_id: str
    project_id: str
    export_id: str
    storage_key: str


class StorageConsistencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_photo_storage_references(self) -> list[PhotoStorageReference]:
        result = await self.session.execute(
            select(
                Project.organization_id,
                ProjectPhoto.project_id,
                ProjectPhoto.id,
                ProjectPhoto.storage_key,
                ProjectPhoto.preview_storage_key,
                ProjectPhoto.ai_input_storage_key,
            )
            .join(Project, Project.id == ProjectPhoto.project_id)
            .where(ProjectPhoto.status == "active")
            .order_by(Project.organization_id.asc(), ProjectPhoto.project_id.asc(), ProjectPhoto.id.asc())
        )

        references: list[PhotoStorageReference] = []
        for organization_id, project_id, photo_id, storage_key, preview_storage_key, ai_input_storage_key in result.all():
            references.append(
                PhotoStorageReference(
                    organization_id=organization_id,
                    project_id=project_id,
                    photo_id=photo_id,
                    storage_key=storage_key,
                    variant="original",
                )
            )
            if preview_storage_key:
                references.append(
                    PhotoStorageReference(
                        organization_id=organization_id,
                        project_id=project_id,
                        photo_id=photo_id,
                        storage_key=preview_storage_key,
                        variant="preview",
                    )
                )
            if ai_input_storage_key:
                references.append(
                    PhotoStorageReference(
                        organization_id=organization_id,
                        project_id=project_id,
                        photo_id=photo_id,
                        storage_key=ai_input_storage_key,
                        variant="ai_input",
                    )
                )
        return references

    async def list_export_storage_references(self) -> list[ExportStorageReference]:
        result = await self.session.execute(
            select(
                Project.organization_id,
                ProjectExport.project_id,
                ProjectExport.id,
                ProjectExport.storage_key,
            )
            .join(Project, Project.id == ProjectExport.project_id)
            .where(
                ProjectExport.storage_key.is_not(None),
                ProjectExport.status == "completed",
            )
            .order_by(Project.organization_id.asc(), ProjectExport.project_id.asc(), ProjectExport.id.asc())
        )
        return [
            ExportStorageReference(
                organization_id=organization_id,
                project_id=project_id,
                export_id=export_id,
                storage_key=storage_key,
            )
            for organization_id, project_id, export_id, storage_key in result.all()
            if storage_key
        ]

    async def get_project_org_map(self, project_ids: set[str]) -> dict[str, str]:
        if not project_ids:
            return {}

        result = await self.session.execute(
            select(Project.id, Project.organization_id)
            .where(Project.id.in_(project_ids))
            .order_by(Project.id.asc())
        )
        return {project_id: organization_id for project_id, organization_id in result.all()}
