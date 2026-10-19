from datetime import datetime
from pydantic import BaseModel


class AuthUserRead(BaseModel):
    id: str
    email: str
    fullName: str
    role: str
    isActive: bool
    organizationId: str
    isSuperAdmin: bool = False
    impersonatedBy: str | None = None  # set when token was issued via /admin/impersonate


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    user: AuthUserRead
    sessionId: str | None = None


class LogoutRequest(BaseModel):
    refreshToken: str


class LogoutResponse(BaseModel):
    message: str


class RefreshRequest(BaseModel):
    refreshToken: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class ChangePasswordResponse(BaseModel):
    message: str


class AuthSessionRead(BaseModel):
    id: str
    createdAt: datetime
    accessExpiresAt: datetime
    refreshExpiresAt: datetime
    revokedAt: datetime | None = None
    isCurrent: bool = False


class AuthSessionListResponse(BaseModel):
    items: list[AuthSessionRead]


class ForgotPasswordRequest(BaseModel):
    email: str


class ForgotPasswordResponse(BaseModel):
    message: str  # always the same — never reveal whether the email exists


class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str


class ResetPasswordResponse(BaseModel):
    message: str
