from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.repositories.token_repository import (
    TOKEN_STATE_ACTIVE,
    TokenStateBackendUnavailableError,
)
from app.schemas.auth import LogoutRequest, RefreshRequest
from app.services.auth_service import AuthService, RefreshResult


_JWT_SECRET = "test-e2e-jwt-secret-x99-32bytes-min"
_JWT_ALGO = "HS256"


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.jwt_secret = _JWT_SECRET
    settings.jwt_algorithm = _JWT_ALGO
    settings.jwt_refresh_token_expire_days = 30
    settings.jwt_access_token_expire_minutes = 15
    return settings


def _make_user(*, password_hash: str = "$2b$12$invalid-invalid-invalid-invalid-invalid-invalidinv") -> MagicMock:
    user = MagicMock()
    user.id = "usr_auth_hardening"
    user.email = "auth-hardening@test.local"
    user.password_hash = password_hash
    user.is_active = True
    user.tokens_valid_after = None
    user.token_version = 0
    user.full_name = "Auth Hardening User"
    user.role = "manager"
    user.organization_id = "org_test"
    user.is_superadmin = False
    return user


def _make_service(user: MagicMock | None = None) -> AuthService:
    session = MagicMock()
    session.get = AsyncMock(return_value=user)

    tokens = MagicMock()
    tokens.get_token_state = AsyncMock(return_value=TOKEN_STATE_ACTIVE)
    tokens.revoke = AsyncMock(return_value=True)
    tokens.create_user_session = AsyncMock()
    tokens.rotate_user_session = AsyncMock()

    service = AuthService.__new__(AuthService)
    service.session = session
    service._settings = _make_settings()
    service._tokens = tokens
    return service


def _encode_refresh_token(payload: dict) -> str:
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


class TestAuthServiceHardening:
    @pytest.mark.asyncio
    async def test_login_fails_closed_for_corrupted_password_hash(self):
        user = _make_user(password_hash="definitely-not-a-bcrypt-hash")
        service = _make_service(user)
        service.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: user))

        result = await service.login(email=user.email, password="AnyPassword99!")

        assert result is None

    @pytest.mark.asyncio
    async def test_refresh_fails_closed_for_token_missing_jti(self):
        user = _make_user(password_hash="$2b$12$abcdefghijklmnopqrstuv123456789012345678901234567890")
        service = _make_service(user)
        token = _encode_refresh_token(
            {
                "sub": user.id,
                "type": "refresh",
                "exp": datetime.now(UTC) + timedelta(days=30),
            }
        )

        result = await service.refresh(token)

        assert result is None
        service._tokens.get_token_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revoke_token_returns_false_for_invalid_or_expired_payload(self):
        service = _make_service()

        expired_token = _encode_refresh_token(
            {
                "sub": "usr_auth_hardening",
                "jti": "expired-jti",
                "type": "refresh",
                "exp": datetime.now(UTC) - timedelta(seconds=5),
            }
        )

        assert await service.revoke_token(" malformed-token ") is False
        assert await service.revoke_token(expired_token) is False


class TestAuthRouteHardening:
    @pytest.mark.asyncio
    async def test_refresh_route_logs_reuse_reason_without_token_leak(self):
        from app.api.routes.auth import refresh

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/refresh",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        service = AsyncMock(spec=AuthService)
        service.refresh_with_status = AsyncMock(
            return_value=RefreshResult(tokens=None, failure_reason="revoked_or_reused_token")
        )

        with patch("app.api.routes.auth.logger.warning") as mock_warning:
            with pytest.raises(HTTPException) as exc_info:
                await refresh(
                    request=request,
                    payload=RefreshRequest(refreshToken="refresh-token-secret"),
                    service=service,
                )

        assert exc_info.value.status_code == 401
        mock_warning.assert_called_once()
        assert "refresh-token-secret" not in repr(mock_warning.call_args)

    @pytest.mark.asyncio
    async def test_refresh_route_returns_503_when_token_state_backend_is_unavailable(self):
        from app.api.routes.auth import refresh

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/refresh",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        service = AsyncMock(spec=AuthService)
        service.refresh_with_status = AsyncMock(
            side_effect=TokenStateBackendUnavailableError(
                operation="get_token_state",
                jti="refresh-jti",
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await refresh(
                request=request,
                payload=RefreshRequest(refreshToken="refresh-token-secret"),
                service=service,
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_logout_route_logs_without_token_leak(self):
        from app.api.routes.auth import logout

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/logout",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        service = AsyncMock(spec=AuthService)
        service.revoke_session_by_token = AsyncMock(side_effect=[True, False])
        service.revoke_token = AsyncMock(side_effect=[False, True])

        with patch("app.api.routes.auth.logger.info") as mock_info:
            response = await logout(
                request=request,
                payload=LogoutRequest(refreshToken="bad-refresh-token"),
                authorization="Bearer valid-access-token",
                service=service,
            )

        assert response.message == "Logged out."
        assert service.revoke_token.await_count == 2
        assert "bad-refresh-token" not in repr(mock_info.call_args)
        assert "valid-access-token" not in repr(mock_info.call_args)

    @pytest.mark.asyncio
    async def test_logout_route_returns_503_when_token_state_backend_is_unavailable(self):
        from app.api.routes.auth import logout

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/auth/logout",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        service = AsyncMock(spec=AuthService)
        service.revoke_session_by_token = AsyncMock(
            side_effect=TokenStateBackendUnavailableError(
                operation="cache_revoked_token",
                jti="logout-jti",
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await logout(
                request=request,
                payload=LogoutRequest(refreshToken="refresh-token-secret"),
                authorization="Bearer access-token",
                service=service,
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_current_user_returns_503_when_token_state_backend_is_unavailable(self):
        from app.api.deps import get_current_user

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/auth/me",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        service = AsyncMock(spec=AuthService)
        service.get_user_by_token = AsyncMock(
            side_effect=TokenStateBackendUnavailableError(
                operation="get_token_state",
                jti="access-jti",
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                request=request,
                authorization="Bearer access-token",
                auth_service=service,
            )

        assert exc_info.value.status_code == 503


class TestAuthLifecycleIntegration:
    @pytest.mark.asyncio
    async def test_refresh_token_reuse_after_rotation_is_rejected(self, app_client, test_tenants):
        login_response = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
        assert login_response.status_code == 200, login_response.text
        original_refresh = login_response.json()["refreshToken"]

        refresh_response = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": original_refresh},
        )
        assert refresh_response.status_code == 200, refresh_response.text
        rotated_refresh = refresh_response.json()["refreshToken"]

        reused_response = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": original_refresh},
        )
        assert reused_response.status_code == 401, reused_response.text

        fresh_response = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": rotated_refresh},
        )
        assert fresh_response.status_code == 200, fresh_response.text

    @pytest.mark.asyncio
    async def test_logout_with_invalid_refresh_token_still_revokes_access_token(self, app_client, test_tenants):
        login_response = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
        assert login_response.status_code == 200, login_response.text
        access_token = login_response.json()["accessToken"]

        logout_response = await app_client.post(
            "/api/v1/auth/logout",
            json={"refreshToken": " malformed-refresh-token "},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_response.status_code == 200, logout_response.text

        me_response = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_response.status_code == 401, me_response.text

    @pytest.mark.asyncio
    async def test_login_and_refresh_return_stable_session_id(self, app_client, test_tenants):
        login_response = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
        assert login_response.status_code == 200, login_response.text
        session_id = login_response.json()["sessionId"]
        assert isinstance(session_id, str) and session_id.startswith("sess_")

        refresh_response = await app_client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": login_response.json()["refreshToken"]},
        )
        assert refresh_response.status_code == 200, refresh_response.text
        assert refresh_response.json()["sessionId"] == session_id

    @pytest.mark.asyncio
    async def test_user_can_list_and_revoke_specific_session(self, app_client, test_tenants):
        first_login = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
        second_login = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
        assert first_login.status_code == 200, first_login.text
        assert second_login.status_code == 200, second_login.text

        first_access = first_login.json()["accessToken"]
        first_session_id = first_login.json()["sessionId"]
        second_access = second_login.json()["accessToken"]
        second_session_id = second_login.json()["sessionId"]
        assert first_session_id != second_session_id

        sessions_response = await app_client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {first_access}"},
        )
        assert sessions_response.status_code == 200, sessions_response.text
        items = sessions_response.json()["items"]
        assert {item["id"] for item in items} >= {first_session_id, second_session_id}
        current_items = [item for item in items if item["isCurrent"]]
        assert len(current_items) == 1
        assert current_items[0]["id"] == first_session_id

        revoke_response = await app_client.delete(
            f"/api/v1/auth/sessions/{second_session_id}",
            headers={"Authorization": f"Bearer {first_access}"},
        )
        assert revoke_response.status_code == 200, revoke_response.text

        revoked_me = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {second_access}"},
        )
        assert revoked_me.status_code == 401, revoked_me.text

        current_me = await app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {first_access}"},
        )
        assert current_me.status_code == 200, current_me.text
