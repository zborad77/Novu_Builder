import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import get_auth_service, get_current_user
from app.core.account_limiter import is_account_throttled, record_login_failure, reset_login_failures
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import enforce_password_strength
from app.schemas.auth import (
    AuthUserRead,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
)
from app.core.audit import write_audit_log
from app.core.email import send_password_reset_email
from app.models import PasswordResetToken, User
from app.services.auth_service import AuthService, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().rate_limit_login)
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    settings = get_settings()
    # Reuse the shared Redis client from app state (avoids new connection per login).
    # Falls back to creating its own connection if app state has no Redis client.
    shared_redis = getattr(request.app.state, "job_queue", None)
    # R-08: per-account brute-force guard — checked before any DB work
    if await is_account_throttled(payload.email, settings.redis_url, redis_client=shared_redis):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
    result = await service.login(email=payload.email, password=payload.password)
    if not result:
        await record_login_failure(payload.email, settings.redis_url, redis_client=shared_redis)
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    # Successful login — reset the per-account failure counter
    await reset_login_failures(payload.email, settings.redis_url, redis_client=shared_redis)
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
    authorization: str | None = Header(None),
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    await service.revoke_token(payload.refreshToken)
    if authorization and authorization.startswith("Bearer "):
        await service.revoke_token(authorization[7:])
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
    # Truncate to seconds so tokens issued in the same second are not falsely rejected
    # (JWT exp is integer-second precision; microseconds would cause off-by-one)
    user.tokens_valid_after = datetime.now(UTC).replace(microsecond=0)
    await service.session.commit()
    return ChangePasswordResponse(message="Password changed.")


_RESET_RATE = "5/hour"

# Self-service reset was intentionally retired — current architecture has no supported web client flow.
# Admin reset remains available at POST /api/v1/admin/users/{id}/reset-password.
_RESET_RETIRED_DETAIL = (
    "Self-service password reset is not supported in the current architecture. "
    "Use admin reset workflow."
)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
@limiter.limit(_RESET_RATE)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> ForgotPasswordResponse:
    """Self-service reset retired — no supported web client flow exists."""
    raise HTTPException(status_code=410, detail=_RESET_RETIRED_DETAIL)


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit(_RESET_RATE)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
) -> ResetPasswordResponse:
    """Self-service reset retired — no supported web client flow exists."""
    raise HTTPException(status_code=410, detail=_RESET_RETIRED_DETAIL)
