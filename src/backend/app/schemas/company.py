from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.rbac import TenantRole

# Write payloads reject unknown fields (organizationId on PATCH, isSuperAdmin,
# tenant_id, …) instead of silently ignoring them, so mass-assignment attempts
# fail loudly with 422.
_WRITE_MODEL_CONFIG = ConfigDict(extra="forbid")


class CompanyRead(BaseModel):
    id: str
    name: str
    ico: str | None
    email: str | None
    phone: str | None
    defaultCurrency: str
    userCount: int = 0
    createdAt: datetime | None = None


class CompanyCreate(BaseModel):
    model_config = _WRITE_MODEL_CONFIG

    name: str
    ico: str | None = None
    email: str | None = None
    phone: str | None = None
    defaultCurrency: str = "CZK"


class CompanyPatch(BaseModel):
    model_config = _WRITE_MODEL_CONFIG

    name: str | None = None
    ico: str | None = None
    email: str | None = None
    phone: str | None = None
    defaultCurrency: str | None = None


class CompanyListResponse(BaseModel):
    items: list[CompanyRead]
    total: int
    limit: int
    offset: int
    hasMore: bool


class AdminUserRead(BaseModel):
    id: str
    organizationId: str
    organizationName: str | None = None
    email: str
    fullName: str
    role: str
    isActive: bool
    isSuperAdmin: bool
    createdAt: datetime | None = None


class AdminUserCreate(BaseModel):
    model_config = _WRITE_MODEL_CONFIG

    organizationId: str
    email: str
    fullName: str
    # Only tenant roles are accepted; "superadmin" is never assignable via API.
    role: TenantRole = "technician"
    password: str
    isActive: bool = True


class AdminUserPatch(BaseModel):
    model_config = _WRITE_MODEL_CONFIG

    fullName: str | None = None
    role: TenantRole | None = None
    isActive: bool | None = None
    password: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int
    hasMore: bool
