import secrets
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import get_auth_service, get_current_user
from app.core.account_limiter import is_account_throttled, record_login_failure, reset_login_failures
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.metrics import AUTH_FAILURES_TOTAL
from app.core.security import enforce_password_strength
from app.schemas.auth import (
    AuthUserRead,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    ResetPasswordResponse,
)
from app.core.audit import SecurityAuditWriteError, commit_security_critical_audit
from app.core.email import send_password_reset_email
from app.models import PasswordResetToken, User
from app.services.auth_service import AuthService, hash_password

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _email_domain(email: str) -> str | None:
    parts = email.strip().lower().split("@", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _record_auth_failure(endpoint: str, reason: str) -> None:
    AUTH_FAILURES_TOTAL.labels(endpoint=endpoint, reason=reason).inc()


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
        _record_auth_failure("login", "account_throttled")
        logger.warning(
            "SECURITY_EVENT: auth_login_throttled",
            client_ip=_client_ip(request),
            email_domain=_email_domain(payload.email),
        )
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
    result = await service.login(email=payload.email, password=payload.password)
    if not result:
        await record_login_failure(payload.email, settings.redis_url, redis_client=shared_redis)
        _record_auth_failure("login", "invalid_credentials")
        logger.warning(
            "SECURITY_EVENT: auth_login_failed",
            reason="invalid_credentials",
            client_ip=_client_ip(request),
            email_domain=_email_domain(payload.email),
        )
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
        _record_auth_failure("refresh", "missing_token")
        raise HTTPException(status_code=400, detail="refreshToken is required.")
    refresh_result = await service.refresh_with_status(payload.refreshToken)
    if not refresh_result.tokens:
        _record_auth_failure(
            "refresh",
            refresh_result.failure_reason or "invalid_or_expired_token",
        )
        logger.warning(
            "SECURITY_EVENT: auth_refresh_failed",
            reason=refresh_result.failure_reason or "invalid_or_expired_token",
            client_ip=_client_ip(request),
        )
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
    access_token, refresh_token, user = refresh_result.tokens
    return LoginResponse(accessToken=access_token, refreshToken=refresh_token, user=user)


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit(get_settings().rate_limit_login)
async def logout(
    request: Request,
    payload: LogoutRequest,
    authorization: str | None = Header(None),
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    refresh_revoked = await service.revoke_token(payload.refreshToken)
    access_revoked = False
    if authorization and authorization.startswith("Bearer "):
        access_revoked = await service.revoke_token(authorization[7:])
    logger.info(
        "auth.logout_completed",
        client_ip=_client_ip(request),
        access_token_present=bool(authorization and authorization.startswith("Bearer ")),
        access_token_revoked=access_revoked,
        refresh_token_revoked=refresh_revoked,
    )
    return LogoutResponse(message="Logged out.")


@router.get("/me", response_model=AuthUserRead)
async def me(
    current_user: AuthUserRead = Depends(get_current_user),
) -> AuthUserRead:
    return current_user


@router.post("/change-password", response_model=ChangePasswordResponse)
@limiter.limit(get_settings().rate_limit_login)
async def change_password(
    request: Request,
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
        _record_auth_failure("change_password", "invalid_current_password")
        logger.warning(
            "SECURITY_EVENT: auth_change_password_failed",
            reason="invalid_current_password",
            client_ip=_client_ip(request),
            user_id=current_user.id,
            organization_id=current_user.organizationId,
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    user = await service.session.get(User, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.password_hash = hash_password(payload.newPassword)
    # Truncate to seconds so tokens issued in the same second are not falsely rejected
    # (JWT exp is integer-second precision; microseconds would cause off-by-one)
    user.tokens_valid_after = datetime.now(UTC).replace(microsecond=0)
    try:
        await commit_security_critical_audit(
            service.session,
            current_user_id=current_user.id,
            action="auth.change_password",
            resource_type="user",
            resource_id=current_user.id,
            detail={"organization_id": current_user.organizationId},
        )
    except SecurityAuditWriteError as exc:
        await service.session.rollback()
        logger.error(
            "auth.change_password_audit_enforcement_failed",
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc
    logger.info(
        "auth.change_password_completed",
        client_ip=_client_ip(request),
        user_id=current_user.id,
        organization_id=current_user.organizationId,
    )
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
) -> ForgotPasswordResponse:
    """Self-service reset retired — no supported web client flow exists."""
    logger.warning(
        "auth.reset_retired_called",
        endpoint="forgot-password",
        client_ip=request.client.host if request.client else None,
    )
    raise HTTPException(status_code=410, detail=_RESET_RETIRED_DETAIL)


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit(_RESET_RATE)
async def reset_password(
    request: Request,
) -> ResetPasswordResponse:
    """Self-service reset retired — no supported web client flow exists."""
    logger.warning(
        "auth.reset_retired_called",
        endpoint="reset-password",
        client_ip=request.client.host if request.client else None,
    )
    raise HTTPException(status_code=410, detail=_RESET_RETIRED_DETAIL)
