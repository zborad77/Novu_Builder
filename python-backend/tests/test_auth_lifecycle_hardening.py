from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

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
    user.full_name = "Auth Hardening User"
    user.role = "manager"
    user.organization_id = "org_test"
    user.is_superadmin = False
    return user


def _make_service(user: MagicMock | None = None) -> AuthService:
    session = MagicMock()
    session.get = AsyncMock(return_value=user)

    tokens = MagicMock()
    tokens.is_revoked = AsyncMock(return_value=False)
    tokens.revoke = AsyncMock(return_value=True)

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
        service._tokens.is_revoked.assert_not_awaited()

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

        request = MagicMock()
        request.client.host = "127.0.0.1"
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
    async def test_logout_route_logs_without_token_leak(self):
        from app.api.routes.auth import logout

        request = MagicMock()
        request.client.host = "127.0.0.1"
        service = AsyncMock(spec=AuthService)
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
