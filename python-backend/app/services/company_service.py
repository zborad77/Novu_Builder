from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.rbac import SUPERADMIN_ROLE
from app.models import Organization, User
from app.schemas.company import (
    AdminUserCreate,
    AdminUserPatch,
    AdminUserRead,
    CompanyCreate,
    CompanyPatch,
    CompanyRead,
)
from app.services.auth_service import AuthService, hash_password


def _org_to_read(org: Organization, user_count: int = 0) -> CompanyRead:
    return CompanyRead(
        id=org.id,
        name=org.name,
        ico=org.ico,
        email=org.email,
        phone=org.phone,
        defaultCurrency=org.default_currency,
        userCount=user_count,
        createdAt=org.created_at,
    )


def _user_to_admin_read(user: User, org_name: str | None = None) -> AdminUserRead:
    return AdminUserRead(
        id=user.id,
        organizationId=user.organization_id,
        organizationName=org_name,
        email=user.email,
        fullName=user.full_name,
        role=user.role,
        isActive=user.is_active,
        isSuperAdmin=user.is_superadmin,
        createdAt=user.created_at,
    )


class CompanyService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def write_audit_log(
        self,
        *,
        current_user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: dict,
    ) -> None:
        await write_audit_log(
            self.session,
            current_user_id=current_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )

    # ── Organizations ────────────────────────────────────────────────────────

    async def list_companies(
        self,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[CompanyRead], int]:
        total_result = await self.session.execute(select(func.count(Organization.id)))
        total = int(total_result.scalar_one() or 0)

        result = await self.session.execute(
            select(Organization)
            .order_by(Organization.name, Organization.id)
            .offset(offset)
            .limit(limit)
        )
        orgs = result.scalars().all()
        if not orgs:
            return [], total

        org_ids = [org.id for org in orgs]
        count_result = await self.session.execute(
            select(User.organization_id, func.count(User.id))
            .where(User.organization_id.in_(org_ids))
            .group_by(User.organization_id)
        )
        counts: dict[str, int] = {
            organization_id: int(user_count)
            for organization_id, user_count in count_result.all()
        }

        return [_org_to_read(org, counts.get(org.id, 0)) for org in orgs], total

    async def get_company(self, company_id: str) -> CompanyRead | None:
        org = await self.session.get(Organization, company_id)
        if not org:
            return None
        count_result = await self.session.execute(
            select(func.count(User.id)).where(User.organization_id == company_id)
        )
        user_count = count_result.scalar_one()
        return _org_to_read(org, user_count)

    async def create_company(self, payload: CompanyCreate) -> CompanyRead:
        org_id = f"org_{uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name=payload.name.strip(),
            ico=payload.ico,
            email=payload.email,
            phone=payload.phone,
            default_currency=payload.defaultCurrency,
        )
        self.session.add(org)
        await self.session.commit()
        await self.session.refresh(org)
        return _org_to_read(org, 0)

    async def patch_company(self, company_id: str, payload: CompanyPatch) -> CompanyRead | None:
        org = await self.session.get(Organization, company_id)
        if not org:
            return None
        changes = payload.model_dump(exclude_unset=True)
        field_map = {
            "name": "name",
            "ico": "ico",
            "email": "email",
            "phone": "phone",
            "defaultCurrency": "default_currency",
        }
        for schema_key, model_key in field_map.items():
            if schema_key in changes:
                setattr(org, model_key, changes[schema_key])
        await self.session.commit()
        await self.session.refresh(org)
        return await self.get_company(company_id)

    # ── Users ─────────────────────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        organization_id: str | None = None,
        exclude_superadmins: bool = False,
        limit: int,
        offset: int,
    ) -> tuple[list[AdminUserRead], int]:
        filters = []
        if organization_id:
            filters.append(User.organization_id == organization_id)
        if exclude_superadmins:
            filters.append(User.is_superadmin.is_(False))
            filters.append(User.role != SUPERADMIN_ROLE)

        count_query = select(func.count(User.id)).select_from(User).where(*filters)
        total_result = await self.session.execute(count_query)
        total = int(total_result.scalar_one() or 0)

        query = (
            select(User, Organization.name)
            .join(Organization, User.organization_id == Organization.id)
            .where(*filters)
        )
        query = query.order_by(Organization.name, User.full_name, User.id).offset(offset).limit(limit)
        result = await self.session.execute(query)
        return [_user_to_admin_read(user, org_name) for user, org_name in result.all()], total

    async def get_user(self, user_id: str) -> AdminUserRead | None:
        result = await self.session.execute(
            select(User, Organization.name)
            .join(Organization, User.organization_id == Organization.id)
            .where(User.id == user_id)
        )
        row = result.one_or_none()
        if not row:
            return None
        user, org_name = row
        return _user_to_admin_read(user, org_name)

    async def get_user_model(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def create_user(self, payload: AdminUserCreate, *, commit: bool = True) -> AdminUserRead | None:
        org = await self.session.get(Organization, payload.organizationId)
        if not org:
            return None
        # Check email uniqueness
        existing = await self.session.execute(select(User).where(User.email == payload.email.strip().lower()))
        if existing.scalar_one_or_none():
            raise ValueError(f"Email {payload.email} is already in use.")
        user = User(
            id=f"usr_{uuid4().hex[:8]}",
            organization_id=payload.organizationId,
            email=payload.email.strip().lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.fullName.strip(),
            role=payload.role,
            is_active=payload.isActive,
            # Superadmins are created only with the server CLI, never via API.
            is_superadmin=False,
        )
        self.session.add(user)
        if commit:
            await self.session.commit()
            await self.session.refresh(user)
        else:
            await self.session.flush()
        return _user_to_admin_read(user, org.name)

    def apply_user_patch(self, user: User, payload: AdminUserPatch, *, now: datetime) -> None:
        """Stage profile/role/activation/password changes without committing.

        Authorization is the caller's job (app.core.rbac). A password change
        always invalidates every token issued before ``now``.
        """
        if payload.fullName is not None:
            user.full_name = payload.fullName.strip()
        if payload.role is not None:
            user.role = payload.role
        if payload.isActive is not None:
            user.is_active = payload.isActive
        if payload.password is not None:
            user.password_hash = hash_password(payload.password)
            AuthService.invalidate_user_token_state(user, now=now)
