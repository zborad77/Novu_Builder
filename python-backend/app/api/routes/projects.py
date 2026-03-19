from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_project_service
from app.schemas.project import (
    ProjectCreate,
    ProjectCreateResponse,
    ProjectDetail,
    ProjectDuplicateRequest,
    ProjectListResponse,
    ProjectPatch,
    ProjectProposalDraftPatch,
)
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


@router.post("/{project_id}/duplicate", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project_id: str,
    payload: ProjectDuplicateRequest,
    service: ProjectService = Depends(get_project_service),
) -> ProjectCreateResponse:
    try:
        duplicated = await service.duplicate_project(project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not duplicated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return ProjectCreateResponse(id=duplicated.id, status=duplicated.status)


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


@router.patch("/{project_id}/proposal-draft", response_model=ProjectDetail)
async def patch_project_proposal_draft(
    project_id: str,
    payload: ProjectProposalDraftPatch,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_proposal_draft(
        project_id,
        payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated


@router.post("/{project_id}/final-proposal", response_model=ProjectDetail)
async def create_project_final_proposal(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    try:
        updated = await service.create_final_proposal(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated


@router.post("/{project_id}/send", response_model=ProjectDetail)
async def send_project(
    project_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    try:
        updated = await service.mark_project_sent(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated
