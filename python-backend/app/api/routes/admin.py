from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_superadmin
from app.db.session import get_db_session
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
