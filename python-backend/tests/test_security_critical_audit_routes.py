from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.schemas.auth import AuthUserRead


def _current_user(*, user_id: str = "usr-1", org_id: str = "org-1", is_superadmin: bool = False) -> AuthUserRead:
    return AuthUserRead(
        id=user_id,
        email="user@test.local",
        fullName="User",
        role="superadmin" if is_superadmin else "manager",
        isActive=True,
        organizationId=org_id,
        isSuperAdmin=is_superadmin,
        impersonatedBy=None,
    )


def _request(*, client_host: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [],
            "client": (client_host, 12345),
        }
    )


@pytest.mark.asyncio
async def test_change_password_returns_503_when_security_audit_enforcement_fails():
    from app.api.routes.auth import change_password
    from app.core.audit import SecurityAuditWriteError
    from app.schemas.auth import ChangePasswordRequest

    service = MagicMock()
    service.login = AsyncMock(return_value=("access", "refresh", _current_user()))
    service.change_password = AsyncMock(side_effect=SecurityAuditWriteError("audit unavailable"))

    with (
        patch("app.api.routes.auth.is_account_throttled", new=AsyncMock(return_value=False)),
        patch("app.api.routes.auth.reset_login_failures", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await change_password(
                request=_request(),
                payload=ChangePasswordRequest(currentPassword="CurrentPass1!", newPassword="NewPass123!"),
                current_user=_current_user(),
                service=service,
            )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_reset_user_password_returns_503_when_security_audit_enforcement_fails():
    from app.api.routes.admin import ResetPasswordPayload, reset_user_password
    from app.core.audit import SecurityAuditWriteError

    target = SimpleNamespace(
        id="usr-target",
        email="target@test.local",
        organization_id="org-1",
        password_hash="old-hash",
        tokens_valid_after=None,
        token_version=0,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=target)

    with patch(
        "app.api.routes.admin.commit_security_critical_audit",
        new=AsyncMock(side_effect=SecurityAuditWriteError("audit unavailable")),
    ), patch(
        "app.api.routes.admin.TokenRepository.revoke_all_user_sessions",
        new=AsyncMock(return_value=[]),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await reset_user_password(
                request=_request(),
                user_id="usr-target",
                payload=ResetPasswordPayload(password="NewPass123!"),
                current_user=_current_user(user_id="admin-1"),
                session=session,
                auth_redis=None,
            )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_impersonate_user_returns_503_when_security_audit_enforcement_fails():
    from app.api.routes.admin import impersonate_user
    from app.core.audit import SecurityAuditWriteError

    target = SimpleNamespace(
        id="usr-target",
        email="target@test.local",
        full_name="Target User",
        organization_id="org-1",
        role="manager",
        is_superadmin=False,
    )
    session = AsyncMock()
    session.get = AsyncMock(return_value=target)

    with patch(
        "app.api.routes.admin.commit_security_critical_audit",
        new=AsyncMock(side_effect=SecurityAuditWriteError("audit unavailable")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await impersonate_user(
                request=_request(),
                user_id="usr-target",
                current_user=_current_user(user_id="admin-1", is_superadmin=True),
                session=session,
            )

    assert exc_info.value.status_code == 503
