from typing import Annotated, NoReturn

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.api.deps import get_auth_redis, get_auth_service, get_current_user
from app.core.account_limiter import (
    AccountThrottleBackendUnavailableError,
    is_account_throttled,
    record_login_failure,
    reset_login_failures,
)
from app.core.audit import SecurityAuditWriteError
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.metrics import AUTH_FAILURES_TOTAL, metric_labels, normalize_tenant_metric_label
from app.core.security import enforce_password_strength
from app.repositories.token_repository import TokenStateBackendUnavailableError
from app.schemas.auth import (
    AuthSessionListResponse,
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
from app.services.auth_service import AuthService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _email_domain(email: str) -> str | None:
    parts = email.strip().lower().split("@", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def _record_auth_failure(
    endpoint: str,
    reason: str,
    tenant_id: str | None = None,
    *,
    is_superadmin_context: bool = False,
) -> None:
    metric_labels(
        AUTH_FAILURES_TOTAL,
        endpoint=endpoint,
        reason=reason,
        tenant_id=normalize_tenant_metric_label(
            tenant_id,
            is_superadmin_context=is_superadmin_context,
        ),
    ).inc()


def _raise_auth_protection_unavailable(
    request: Request,
    *,
    endpoint: str,
    email: str,
    operation: str,
    error: Exception,
    user_id: str | None = None,
    organization_id: str | None = None,
    is_superadmin_context: bool = False,
) -> NoReturn:
    _record_auth_failure(
        endpoint,
        "auth_protection_unavailable",
        tenant_id=organization_id,
        is_superadmin_context=is_superadmin_context,
    )
    logger.error(
        "SECURITY_EVENT: auth_protection_unavailable",
        endpoint=endpoint,
        operation=operation,
        client_ip=_client_ip(request),
        email_domain=_email_domain(email),
        user_id=user_id,
        organization_id=organization_id,
        error=str(error),
    )
    raise HTTPException(
        status_code=503,
        detail="Authentication protection temporarily unavailable. Retry later.",
    )


def _raise_token_state_unavailable(
    request: Request,
    *,
    endpoint: str,
    operation: str,
    error: Exception,
    user_id: str | None = None,
    organization_id: str | None = None,
    is_superadmin_context: bool = False,
) -> NoReturn:
    _record_auth_failure(
        endpoint,
        "token_state_unavailable",
        tenant_id=organization_id,
        is_superadmin_context=is_superadmin_context,
    )
    logger.error(
        "SECURITY_EVENT: auth_token_state_unavailable",
        endpoint=endpoint,
        operation=operation,
        client_ip=_client_ip(request),
        user_id=user_id,
        organization_id=organization_id,
        error=str(error),
    )
    raise HTTPException(
        status_code=503,
        detail="Authentication token validation unavailable. Retry later.",
    )


async def _revoke_login_result(
    service: AuthService,
    result: tuple[str, str, AuthUserRead] | None,
    *,
    endpoint: str,
    user_id: str | None,
    organization_id: str | None,
) -> None:
    if result is None:
        return

    access_token, refresh_token, _ = result
    session_revoked = False
    access_revoked = False
    refresh_revoked = False
    try:
        session_revoked = await service.revoke_session_by_token(access_token)
        access_revoked = await service.revoke_token(access_token)
        refresh_revoked = await service.revoke_token(refresh_token)
    except Exception as exc:
        logger.error(
            "auth.protection_guard_revoke_failed",
            endpoint=endpoint,
            user_id=user_id,
            organization_id=organization_id,
            error=str(exc),
        )
        return

    logger.warning(
        "auth.protection_guard_reverted_login",
        endpoint=endpoint,
        user_id=user_id,
        organization_id=organization_id,
        session_revoked=session_revoked,
        access_revoked=access_revoked,
        refresh_revoked=refresh_revoked,
    )


async def _enforce_account_throttle(
    request: Request,
    *,
    endpoint: str,
    email: str,
    auth_redis=None,
    user_id: str | None = None,
    organization_id: str | None = None,
    is_superadmin_context: bool = False,
):
    settings = get_settings()
    shared_redis = auth_redis
    try:
        throttled = await is_account_throttled(
            email,
            settings.redis_url,
            redis_client=shared_redis,
        )
    except AccountThrottleBackendUnavailableError as exc:
        _raise_auth_protection_unavailable(
            request,
            endpoint=endpoint,
            email=email,
            operation=exc.operation,
            error=exc,
            user_id=user_id,
            organization_id=organization_id,
            is_superadmin_context=is_superadmin_context,
        )
    if throttled:
        _record_auth_failure(
            endpoint,
            "account_throttled",
            tenant_id=organization_id,
            is_superadmin_context=is_superadmin_context,
        )
        logger.warning(
            "SECURITY_EVENT: auth_account_throttled",
            endpoint=endpoint,
            client_ip=_client_ip(request),
            email_domain=_email_domain(email),
            user_id=user_id,
            organization_id=organization_id,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Please try again later.",
        )

    return settings, shared_redis


@router.post("/login", response_model=LoginResponse)
@limiter.limit(get_settings().rate_limit_login)
async def login(
    request: Request,
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    auth_redis: Annotated[object | None, Depends(get_auth_redis)] = None,
) -> LoginResponse:
    settings, shared_redis = await _enforce_account_throttle(
        request,
        endpoint="login",
        email=payload.email,
        auth_redis=auth_redis,
    )
    result = await service.login(email=payload.email, password=payload.password)
    if not result:
        try:
            await record_login_failure(payload.email, settings.redis_url, redis_client=shared_redis)
        except AccountThrottleBackendUnavailableError as exc:
            _raise_auth_protection_unavailable(
                request,
                endpoint="login",
                email=payload.email,
                operation=exc.operation,
                error=exc,
            )
        _record_auth_failure("login", "invalid_credentials")
        logger.warning(
            "SECURITY_EVENT: auth_login_failed",
            reason="invalid_credentials",
            client_ip=_client_ip(request),
            email_domain=_email_domain(payload.email),
        )
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    try:
        await reset_login_failures(payload.email, settings.redis_url, redis_client=shared_redis)
    except AccountThrottleBackendUnavailableError as exc:
        await _revoke_login_result(
            service,
            result,
            endpoint="login",
            user_id=result[2].id,
            organization_id=result[2].organizationId,
        )
        _raise_auth_protection_unavailable(
            request,
            endpoint="login",
            email=payload.email,
            operation=exc.operation,
            error=exc,
            user_id=result[2].id,
            organization_id=result[2].organizationId,
            is_superadmin_context=result[2].isSuperAdmin,
        )
    access_token, refresh_token, user = result
    return LoginResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=user,
        sessionId=service.get_token_session_id(access_token),
    )


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
    try:
        refresh_result = await service.refresh_with_status(payload.refreshToken)
    except TokenStateBackendUnavailableError as exc:
        _raise_token_state_unavailable(
            request,
            endpoint="refresh",
            operation=exc.operation,
            error=exc,
        )
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
    return LoginResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=user,
        sessionId=service.get_token_session_id(access_token),
    )


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit(get_settings().rate_limit_login)
async def logout(
    request: Request,
    payload: LogoutRequest,
    authorization: str | None = Header(None),
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    try:
        session_revoked = False
        if authorization and authorization.startswith("Bearer "):
            session_revoked = await service.revoke_session_by_token(authorization[7:])
        if not session_revoked:
            session_revoked = await service.revoke_session_by_token(payload.refreshToken)
        refresh_revoked = await service.revoke_token(payload.refreshToken)
        access_revoked = False
        if authorization and authorization.startswith("Bearer "):
            access_revoked = await service.revoke_token(authorization[7:])
    except TokenStateBackendUnavailableError as exc:
        _raise_token_state_unavailable(
            request,
            endpoint="logout",
            operation=exc.operation,
            error=exc,
        )
    logger.info(
        "auth.logout_completed",
        client_ip=_client_ip(request),
        session_revoked=session_revoked,
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


@router.get("/sessions", response_model=AuthSessionListResponse)
async def list_sessions(
    authorization: str | None = Header(None),
    current_user: AuthUserRead = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> AuthSessionListResponse:
    current_session_id = None
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        current_session_id = service.get_token_session_id(authorization[7:])
    items = await service.list_sessions(
        user_id=current_user.id,
        current_session_id=current_session_id,
    )
    return AuthSessionListResponse(items=items)


@router.delete("/sessions/{session_id}", response_model=LogoutResponse)
@limiter.limit(get_settings().rate_limit_login)
async def revoke_session(
    request: Request,
    session_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponse:
    try:
        revoked = await service.revoke_session(user_id=current_user.id, session_id=session_id)
    except TokenStateBackendUnavailableError as exc:
        _raise_token_state_unavailable(
            request,
            endpoint="revoke_session",
            operation=exc.operation,
            error=exc,
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            is_superadmin_context=current_user.isSuperAdmin,
        )
    if not revoked:
        raise HTTPException(status_code=404, detail="Session not found.")

    logger.info(
        "auth.session_revoked",
        client_ip=_client_ip(request),
        user_id=current_user.id,
        organization_id=current_user.organizationId,
        session_id=session_id,
    )
    return LogoutResponse(message="Session revoked.")


@router.post("/change-password", response_model=ChangePasswordResponse)
@limiter.limit(get_settings().rate_limit_login)
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    authorization: str | None = Header(None),
    current_user: AuthUserRead = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
    auth_redis: Annotated[object | None, Depends(get_auth_redis)] = None,
) -> ChangePasswordResponse:
    if not payload.currentPassword or not payload.newPassword:
        raise HTTPException(status_code=400, detail="Both passwords are required.")
    try:
        enforce_password_strength(payload.newPassword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings, shared_redis = await _enforce_account_throttle(
        request,
        endpoint="change_password",
        email=current_user.email,
        auth_redis=auth_redis,
        user_id=current_user.id,
        organization_id=current_user.organizationId,
        is_superadmin_context=current_user.isSuperAdmin,
    )
    verified = await service.login(email=current_user.email, password=payload.currentPassword)
    if not verified:
        try:
            await record_login_failure(current_user.email, settings.redis_url, redis_client=shared_redis)
        except AccountThrottleBackendUnavailableError as exc:
            _raise_auth_protection_unavailable(
                request,
                endpoint="change_password",
                email=current_user.email,
                operation=exc.operation,
                error=exc,
                user_id=current_user.id,
                organization_id=current_user.organizationId,
                is_superadmin_context=current_user.isSuperAdmin,
            )
        _record_auth_failure(
            "change_password",
            "invalid_current_password",
            tenant_id=current_user.organizationId,
            is_superadmin_context=current_user.isSuperAdmin,
        )
        logger.warning(
            "SECURITY_EVENT: auth_change_password_failed",
            reason="invalid_current_password",
            client_ip=_client_ip(request),
            user_id=current_user.id,
            organization_id=current_user.organizationId,
        )
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    try:
        await reset_login_failures(current_user.email, settings.redis_url, redis_client=shared_redis)
    except AccountThrottleBackendUnavailableError as exc:
        await _revoke_login_result(
            service,
            verified,
            endpoint="change_password",
            user_id=current_user.id,
            organization_id=current_user.organizationId,
        )
        _raise_auth_protection_unavailable(
            request,
            endpoint="change_password",
            email=current_user.email,
            operation=exc.operation,
            error=exc,
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            is_superadmin_context=current_user.isSuperAdmin,
        )
    try:
        changed = await service.change_password(
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            new_password=payload.newPassword,
        )
    except TokenStateBackendUnavailableError as exc:
        _raise_token_state_unavailable(
            request,
            endpoint="change_password",
            operation=exc.operation,
            error=exc,
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            is_superadmin_context=current_user.isSuperAdmin,
        )
    except SecurityAuditWriteError as exc:
        logger.error(
            "auth.change_password_audit_enforcement_failed",
            user_id=current_user.id,
            organization_id=current_user.organizationId,
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Security audit subsystem unavailable. Retry later.") from exc
    if not changed:
        raise HTTPException(status_code=404, detail="User not found.")

    access_token_revoked = False
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        try:
            access_token_revoked = await service.revoke_token(authorization[7:])
        except TokenStateBackendUnavailableError as exc:
            _raise_token_state_unavailable(
                request,
                endpoint="change_password",
                operation=exc.operation,
                error=exc,
                user_id=current_user.id,
                organization_id=current_user.organizationId,
                is_superadmin_context=current_user.isSuperAdmin,
            )
    logger.info(
        "auth.change_password_completed",
        client_ip=_client_ip(request),
        user_id=current_user.id,
        organization_id=current_user.organizationId,
        access_token_revoked=access_token_revoked,
    )
    return ChangePasswordResponse(message="Password changed.")


_RESET_RATE = "5/hour"

# Self-service reset was intentionally retired - current architecture has no supported web client flow.
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
    """Self-service reset retired - no supported web client flow exists."""
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
    """Self-service reset retired - no supported web client flow exists."""
    logger.warning(
        "auth.reset_retired_called",
        endpoint="reset-password",
        client_ip=request.client.host if request.client else None,
    )
    raise HTTPException(status_code=410, detail=_RESET_RETIRED_DETAIL)
