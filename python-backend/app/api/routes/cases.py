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

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=ProjectListResponse)
async def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    updated_from: str | None = Query(default=None),
    updated_to: str | None = Query(default=None),
    page: int | None = Query(default=None),
    search: str | None = Query(default=None),
    service: ProjectService = Depends(get_project_service),
) -> ProjectListResponse:
    del updated_from, updated_to, page
    items = await service.list_projects(status=status_filter, search=search)
    return ProjectListResponse(items=items, total=len(items))


@router.post("", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: ProjectCreate,
    service: ProjectService = Depends(get_project_service),
) -> ProjectCreateResponse:
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Case title is required.")
    case = await service.create_project(payload)
    return ProjectCreateResponse(id=case.id, status=case.status)


@router.get("/{case_id}", response_model=ProjectDetail)
async def get_case(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    detail = await service.get_project_detail(case_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    return detail


@router.post("/{case_id}/duplicate", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_case(
    case_id: str,
    payload: ProjectDuplicateRequest,
    service: ProjectService = Depends(get_project_service),
) -> ProjectCreateResponse:
    try:
        duplicated = await service.duplicate_project(case_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not duplicated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return ProjectCreateResponse(id=duplicated.id, status=duplicated.status)


@router.patch("/{case_id}", response_model=ProjectDetail)
async def patch_case(
    case_id: str,
    payload: ProjectPatch,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_project(case_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.patch("/{case_id}/proposal-draft", response_model=ProjectDetail)
async def patch_case_proposal_draft(
    case_id: str,
    payload: ProjectProposalDraftPatch,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_proposal_draft(case_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.post("/{case_id}/final-proposal", response_model=ProjectDetail)
async def create_case_final_proposal(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    try:
        updated = await service.create_final_proposal(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.post("/{case_id}/archive", response_model=ProjectDetail)
async def archive_case(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_project(case_id, {"status": "archived"})
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.post("/{case_id}/send", response_model=ProjectDetail)
async def send_case(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    try:
        updated = await service.mark_project_sent(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found.")
    return updated


@router.get("/{case_id}/timeline", response_model=list[dict])
async def get_case_timeline(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> list[dict]:
    detail = await service.get_project_detail(case_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Case not found.")
    timeline = [
        {"type": "case_created", "label": "Pripad zalozen", "at": detail.createdAt},
    ]
    if detail.latestAnalysis:
        timeline.append({"type": "analysis_completed", "label": "Analyza dokoncena", "at": detail.latestAnalysis.get("createdAt")})
    if detail.quoteVariants:
        timeline.append({"type": "estimate_ready", "label": "Pripraveny odhad nabidky", "at": detail.quoteVariants[0].get("createdAt")})
    return timeline
