"""Správa uživatelů vlastní firmy firemním adminem (rozhodnutí D-10, F8.4).

Firemní admin (role ``admin``) spravuje uživatele **své** firmy z webu
(zóna gateway) a z desktopu (zóna desktop):

* výpis a detail uživatelů vlastní firmy,
* založení uživatele (firma je vždy firma admina, z požadavku se nebere),
* změna jména, role (jen ``manager`` / ``technician``) a aktivace,
* reset hesla (nastaví nové heslo a odvolá všechny sessions uživatele).

Nikdy: uživatelé jiné firmy (404 jako neexistující), superadmini (neviditelní),
jiní firemní admini a vlastní účet (role, aktivace, heslo – 403), přidělení
role ``admin`` nebo ``superadmin``. Pravidla jsou v ``app.modules.identity.rbac``.

Systémová administrace (``/admin/*``) zůstává jen v zóně admin pro NovuAdmin
přes WG; tento router ji nenahrazuje a neodkrývá.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.platform.http.deps import get_auth_redis
from app.modules.identity.api.deps import get_current_user
from app.modules.identity.api.deps import get_company_service
from app.modules.identity.authz import (
    commit_security_critical_audit_or_503 as _commit_security_critical_audit,
    enforce_rbac_decision as _enforce,
)
from app.platform.config import get_settings
from app.platform.http.limiter import limiter
from app.modules.identity.rbac import TenantRole, assignable_roles, can_manage_user, can_view_user, is_tenant_admin
from app.modules.identity.security import enforce_password_strength
from app.modules.identity.token_repository import SessionTokenRevocation, TokenRepository
from app.modules.identity.schemas.auth import AuthUserRead
from app.modules.identity.schemas.company import AdminUserCreate, AdminUserListResponse, AdminUserPatch, AdminUserRead
from app.modules.identity.auth_service import AuthService, hash_password
from app.modules.identity.company_service import CompanyService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/org", tags=["organization"])

_WRITE = ConfigDict(extra="forbid")


class OrgUserCreate(BaseModel):
    model_config = _WRITE

    email: str
    fullName: str
    role: TenantRole = "technician"
    password: str
    isActive: bool = True


class OrgUserPatch(BaseModel):
    model_config = _WRITE

    fullName: str | None = None
    role: TenantRole | None = None
    isActive: bool | None = None


class OrgUserPasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str


async def require_company_admin(current_user: AuthUserRead = Depends(get_current_user)) -> AuthUserRead:
    """Jen firemní admin jednající sám za sebe (ne superadmin, ne impersonace)."""
    if current_user.impersonatedBy or not is_tenant_admin(current_user):
        logger.warning(
            "SECURITY_EVENT: org_user_admin_denied",
            user_id=current_user.id,
            role=current_user.role,
            impersonated=bool(current_user.impersonatedBy),
        )
        raise HTTPException(status_code=403, detail="Company administrator access required.")
    return current_user


async def _load_target(service: CompanyService, user_id: str, actor: AuthUserRead, operation: str, *, sensitive: bool | None):
    target = await service.get_user_model(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")
    decision = can_view_user(actor, target) if sensitive is None else can_manage_user(actor, target, sensitive=sensitive)
    _enforce(decision, current_user=actor, operation=operation, resource_id=user_id, not_found_detail="User not found.")
    return target


@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit(get_settings().rate_limit_admin)
async def list_org_users(
    request: Request,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_company_admin),
) -> AdminUserListResponse:
    items, total = await service.list_users(
        organization_id=current_user.organizationId,
        exclude_superadmins=True,
        limit=limit,
        offset=offset,
    )
    return AdminUserListResponse(items=items, total=total, limit=limit, offset=offset, hasMore=(offset + len(items)) < total)


@router.post("/users", response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_admin_write)
async def create_org_user(
    request: Request,
    payload: OrgUserCreate,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_company_admin),
) -> AdminUserRead:
    if payload.role not in assignable_roles(current_user):
        _enforce("forbidden", current_user=current_user, operation="org.user.create.role", resource_id=payload.role)
    try:
        enforce_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not current_user.organizationId:  # is_tenant_admin guarantees it; never trust an assert
        raise HTTPException(status_code=403, detail="Company administrator access required.")
    create = AdminUserCreate(
        organizationId=current_user.organizationId,
        email=payload.email,
        fullName=payload.fullName,
        role=payload.role,
        password=payload.password,
        isActive=payload.isActive,
    )
    try:
        user = await service.create_user(create, commit=False)
    except ValueError as exc:
        await service.session.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not user:
        raise HTTPException(status_code=404, detail="Organization not found.")
    await _commit_security_critical_audit(
        service.session,
        current_user=current_user,
        action="org.user.create",
        resource_type="user",
        resource_id=user.id,
        detail={"email": user.email, "role": user.role, "target_org": user.organizationId},
    )
    return user


@router.get("/users/{user_id}", response_model=AdminUserRead)
@limiter.limit(get_settings().rate_limit_admin)
async def get_org_user(
    request: Request,
    user_id: str,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_company_admin),
) -> AdminUserRead:
    await _load_target(service, user_id, current_user, "org.user.get", sensitive=None)
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.patch("/users/{user_id}", response_model=AdminUserRead)
@limiter.limit(get_settings().rate_limit_admin_write)
async def patch_org_user(
    request: Request,
    user_id: str,
    payload: OrgUserPatch,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_company_admin),
    auth_redis: Annotated[object | None, Depends(get_auth_redis)] = None,
) -> AdminUserRead:
    sensitive = payload.role is not None or payload.isActive is not None
    target = await _load_target(service, user_id, current_user, "org.user.patch", sensitive=sensitive)
    if payload.role is not None and payload.role not in assignable_roles(current_user):
        _enforce("forbidden", current_user=current_user, operation="org.user.patch.role", resource_id=user_id)

    now = datetime.now(UTC).replace(microsecond=0)
    service.apply_user_patch(
        target,
        AdminUserPatch(fullName=payload.fullName, role=payload.role, isActive=payload.isActive),
        now=now,
    )
    token_repository = TokenRepository(service.session, redis=auth_redis)
    revocations: list[SessionTokenRevocation] = []
    if payload.isActive is False:
        AuthService.invalidate_user_token_state(target, now=now)
        revocations = await token_repository.revoke_all_user_sessions(target.id, now=now, commit=False)
    await _commit_security_critical_audit(
        service.session,
        current_user=current_user,
        action="org.user.patch",
        resource_type="user",
        resource_id=user_id,
        detail={
            "changes": payload.model_dump(exclude_unset=True),
            "sessions_revoked": len(revocations),
            "target_org": target.organization_id,
        },
    )
    for record in revocations:
        await token_repository.cache_revoked_token(record.jti, record.expires_at)
    updated = await service.get_user(user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(get_settings().rate_limit_admin_sensitive)
async def reset_org_user_password(
    request: Request,
    user_id: str,
    payload: OrgUserPasswordReset,
    service: CompanyService = Depends(get_company_service),
    current_user: AuthUserRead = Depends(require_company_admin),
    auth_redis: Annotated[object | None, Depends(get_auth_redis)] = None,
) -> None:
    target = await _load_target(service, user_id, current_user, "org.user.reset_password", sensitive=True)
    try:
        enforce_password_strength(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    now = datetime.now(UTC).replace(microsecond=0)
    target.password_hash = hash_password(payload.password)
    AuthService.invalidate_user_token_state(target, now=now)
    token_repository = TokenRepository(service.session, redis=auth_redis)
    revocations = await token_repository.revoke_all_user_sessions(target.id, now=now, commit=False)
    await _commit_security_critical_audit(
        service.session,
        current_user=current_user,
        action="org.user.reset_password",
        resource_type="user",
        resource_id=user_id,
        detail={"target_org": target.organization_id, "sessions_revoked": len(revocations)},
    )
    for record in revocations:
        await token_repository.cache_revoked_token(record.jti, record.expires_at)
