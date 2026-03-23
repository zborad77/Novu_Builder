import collections
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superadmin
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.domain import AnalysisJob, Organization, Project
from app.schemas.auth import AuthUserRead
from app.schemas.company import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserPatch,
    AdminUserRead,
    CompanyCreate,
    CompanyListResponse,
    CompanyPatch,
    CompanyRead,
)
from app.services.company_service import CompanyService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_company_service(session: AsyncSession = Depends(get_db_session)) -> CompanyService:
    return CompanyService(session)


# ── Companies ──────────────────────────────────────────────────────────────────

@router.get("/companies", response_model=CompanyListResponse)
async def list_companies(
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyListResponse:
    items = await service.list_companies()
    return CompanyListResponse(items=items, total=len(items))


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyRead:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Company name is required.")
    return await service.create_company(payload)


@router.get("/companies/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: str,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyRead:
    company = await service.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
async def patch_company(
    company_id: str,
    payload: CompanyPatch,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> CompanyRead:
    updated = await service.patch_company(company_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Company not found.")
    return updated


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    org_id: str | None = Query(default=None),
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserListResponse:
    items = await service.list_users(organization_id=org_id)
    return AdminUserListResponse(items=items, total=len(items))


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserRead:
    try:
        user = await service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return user


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def get_user(
    user_id: str,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserRead:
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def patch_user(
    user_id: str,
    payload: AdminUserPatch,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> AdminUserRead:
    updated = await service.patch_user(user_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated


class ResetPasswordPayload(BaseModel):
    password: str


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: str,
    payload: ResetPasswordPayload,
    service: CompanyService = Depends(get_company_service),
    _: AuthUserRead = Depends(require_superadmin),
) -> None:
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    updated = await service.patch_user(user_id, AdminUserPatch(password=payload.password))
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")


# ── Analysis Jobs (all orgs) ───────────────────────────────────────────────────

@router.get("/jobs", response_model=list[dict])
async def list_all_jobs(
    job_status: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
    _: AuthUserRead = Depends(require_superadmin),
) -> list[dict]:
    query = (
        select(AnalysisJob, Project.title, Project.organization_id, Organization.name)
        .join(Project, AnalysisJob.project_id == Project.id)
        .join(Organization, Project.organization_id == Organization.id)
        .order_by(AnalysisJob.created_at.desc())
    )
    if job_status:
        query = query.where(AnalysisJob.status == job_status)

    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "id": job.id,
            "caseId": job.project_id,
            "caseTitle": case_title,
            "orgId": org_id,
            "orgName": org_name,
            "status": job.status,
            "jobType": job.job_type,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
            "errorMessage": job.error_message,
            "createdAt": job.created_at.isoformat(),
        }
        for job, case_title, org_id, org_name in rows
    ]


# ── Logs ───────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[str])
async def get_recent_logs(
    lines: int = Query(default=200, ge=10, le=2000),
    _: AuthUserRead = Depends(require_superadmin),
) -> list[str]:
    settings = get_settings()
    if not settings.log_file:
        raise HTTPException(
            status_code=409,
            detail="Log file not configured. Set LOG_FILE env variable.",
        )
    log_path = Path(settings.log_file)
    if not log_path.exists():
        return []

    # Efficient tail — read last N lines without loading whole file
    with log_path.open("rb") as f:
        deque = collections.deque(maxlen=lines)
        for line in f:
            deque.append(line.decode("utf-8", errors="replace").rstrip())
    return list(deque)
