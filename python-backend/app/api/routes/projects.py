from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_project_service
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectListResponse, ProjectPatch
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    service: ProjectService = Depends(get_project_service),
) -> ProjectListResponse:
    items = await service.list_projects(status=status_filter, search=search)
    return ProjectListResponse(items=items, total=len(items))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
) -> dict:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Project title is required.")

    project = await service.create_project(payload)
    return {
        "id": project.id,
        "status": project.status,
    }


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project_detail(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    detail = await service.get_project_detail(project_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found.")
    return detail


@router.patch("/{project_id}", response_model=ProjectDetail)
async def patch_project(
    project_id: str,
    payload: ProjectPatch,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_project(
        project_id,
        payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated
