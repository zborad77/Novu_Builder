from uuid import uuid4

from app.models import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectSummary


DEFAULT_ORGANIZATION_ID = "org_1"
DEFAULT_CREATED_BY_USER_ID = "usr_1"


def build_project_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        title=project.title,
        status=project.status,
        propertyType=project.property_type,
        repairScope=project.repair_scope,
        addressLabel=project.address_label,
        photoCount=0,
        estimatedAreaSqm=None,
        latestQuoteTotal=None,
        updatedAt=project.updated_at,
    )


def build_project_detail(project: Project) -> ProjectDetail:
    return ProjectDetail(
        id=project.id,
        title=project.title,
        description=project.description,
        status=project.status,
        propertyType=project.property_type,
        repairScope=project.repair_scope,
        location={
            "lat": project.location_lat,
            "lng": project.location_lng,
            "addressLabel": project.address_label,
        },
        client=(
            {
                "id": project.client.id,
                "fullName": project.client.full_name,
                "companyName": project.client.company_name,
                "email": project.client.email,
                "phone": project.client.phone,
            }
            if project.client
            else None
        ),
        photos=[],
        latestAnalysis=None,
        quoteVariants=[],
        createdAt=project.created_at,
        updatedAt=project.updated_at,
    )


class ProjectService:
    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    async def get_project(self, project_id: str) -> Project | None:
        return await self.repository.get_project(project_id)

    async def list_projects(self, *, status: str | None = None, search: str | None = None) -> list[ProjectSummary]:
        projects = await self.repository.list_projects(status=status, search=search)
        return [build_project_summary(project) for project in projects]

    async def get_project_detail(self, project_id: str) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
        if not project:
            return None
        return build_project_detail(project)

    async def create_project(self, payload: ProjectCreate) -> Project:
        project_id = f"prj_{uuid4().hex[:8]}"
        return await self.repository.create_project(
            project_id=project_id,
            organization_id=DEFAULT_ORGANIZATION_ID,
            created_by_user_id=DEFAULT_CREATED_BY_USER_ID,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else "",
            client_id=payload.clientId,
            property_type=payload.propertyType,
            repair_scope=payload.repairScope,
            location_lat=payload.locationLat,
            location_lng=payload.locationLng,
            address_label=payload.addressLabel,
        )

    async def update_project(self, project_id: str, payload: dict) -> ProjectDetail | None:
        project = await self.repository.get_project(project_id)
        if not project:
            return None

        changes = {}
        field_mapping = {
            "title": "title",
            "description": "description",
            "status": "status",
            "propertyType": "property_type",
            "repairScope": "repair_scope",
            "locationLat": "location_lat",
            "locationLng": "location_lng",
            "addressLabel": "address_label",
            "clientId": "client_id",
        }

        for payload_field, model_field in field_mapping.items():
            if payload_field in payload:
                changes[model_field] = payload[payload_field]

        updated = await self.repository.update_project(project, changes)
        return build_project_detail(updated)
