from datetime import datetime

from pydantic import BaseModel


class AuthUserRead(BaseModel):
    id: str
    email: str
    fullName: str
    role: str
    isActive: bool
    organizationId: str


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    user: AuthUserRead


class LogoutResponse(BaseModel):
    message: str


class RefreshRequest(BaseModel):
    refreshToken: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class ChangePasswordResponse(BaseModel):
    message: str
