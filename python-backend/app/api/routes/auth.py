from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_auth_service, get_current_user
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import enforce_password_strength
from app.schemas.auth import (
    AuthUserRead,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
)
from app.models import User
from app.services.auth_service import AuthService, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().rate_limit_login)
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    result = await service.login(email=payload.email, password=payload.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    access_token, refresh_token, user = result
    return LoginResponse(accessToken=access_token, refreshToken=refresh_token, user=user)


@router.post("/refresh", response_model=LoginResponse)
@limiter.limit(get_settings().rate_limit_login)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    if not payload.refreshToken:
        raise HTTPException(status_code=400, detail="refreshToken is required.")
    result = await service.refresh(payload.refreshToken)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
    access_token, refresh_token, user = result
    return LoginResponse(accessToken=access_token, refreshToken=refresh_token, user=user)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    payload: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    await service.revoke_token(payload.refreshToken)
    return LogoutResponse(message="Logged out.")


@router.get("/me", response_model=AuthUserRead)
async def me(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    return current_user


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: AuthUserRead = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> ChangePasswordResponse:
    if not payload.currentPassword or not payload.newPassword:
        raise HTTPException(status_code=400, detail="Both passwords are required.")
    try:
        enforce_password_strength(payload.newPassword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    verified = await service.login(email=current_user.email, password=payload.currentPassword)
    if not verified:
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    user = await service.session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.password_hash = hash_password(payload.newPassword)
    await service.session.commit()
    return ChangePasswordResponse(message="Password changed.")
