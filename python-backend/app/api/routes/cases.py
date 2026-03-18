from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_project_service
from app.schemas.project import ProjectCreate, ProjectCreateResponse, ProjectDetail, ProjectListResponse, ProjectPatch
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


@router.post("/{case_id}/archive", response_model=ProjectDetail)
async def archive_case(
    case_id: str,
    service: ProjectService = Depends(get_project_service),
) -> ProjectDetail:
    updated = await service.update_project(case_id, {"status": "archived"})
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
