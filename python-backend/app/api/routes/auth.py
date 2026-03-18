from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_auth_service
from app.schemas.auth import ChangePasswordRequest, ChangePasswordResponse, LoginRequest, LoginResponse, LogoutResponse, RefreshRequest
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    result = service.login(email=payload.email, password=payload.password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    access_token, refresh_token, user = result
    return LoginResponse(accessToken=access_token, refreshToken=refresh_token, user=user)


@router.post("/logout", response_model=LogoutResponse)
async def logout() -> LogoutResponse:
    return LogoutResponse(message="Logged out.")


@router.get("/me")
async def me(
    service: AuthService = Depends(get_auth_service),
):
    return service.me()


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    if not payload.refreshToken:
        raise HTTPException(status_code=400, detail="refreshToken is required.")
    access_token, refresh_token, user = service.login(email="demo@novu.local", password="demo")
    return LoginResponse(accessToken=access_token, refreshToken=refresh_token, user=user)


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
):
    if not payload.currentPassword or not payload.newPassword:
        raise HTTPException(status_code=400, detail="Both passwords are required.")
    return ChangePasswordResponse(message="Password changed.")
