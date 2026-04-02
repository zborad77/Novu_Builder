from datetime import datetime

from pydantic import BaseModel


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
    name: str
    ico: str | None = None
    email: str | None = None
    phone: str | None = None
    defaultCurrency: str = "CZK"


class CompanyPatch(BaseModel):
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
    organizationId: str
    email: str
    fullName: str
    role: str = "dispatcher"
    password: str
    isActive: bool = True


class AdminUserPatch(BaseModel):
    fullName: str | None = None
    role: str | None = None
    isActive: bool | None = None
    password: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int
    hasMore: bool
