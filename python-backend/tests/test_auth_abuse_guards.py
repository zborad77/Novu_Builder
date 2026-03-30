import builtins
import importlib
import inspect
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.auth import change_password, login, logout, refresh
from app.schemas.auth import AuthUserRead, ChangePasswordRequest, LogoutRequest
from app.services.auth_service import AuthService


def _src(fn) -> str:
    return inspect.getsource(fn)


def _has_limiter_decorator(fn) -> bool:
    return "@limiter.limit(" in _src(fn)


def _current_user() -> AuthUserRead:
    return AuthUserRead(
        id="usr_auth_abuse",
        email="auth-abuse@test.local",
        fullName="Auth Abuse User",
        role="manager",
        isActive=True,
        organizationId="org_test",
        isSuperAdmin=False,
    )


class TestAuthLimiterWiring:
    @pytest.mark.parametrize("endpoint", [login, refresh, logout, change_password])
    def test_sensitive_auth_endpoint_has_limiter_decorator(self, endpoint):
        assert _has_limiter_decorator(endpoint), (
            f"{endpoint.__name__} must have @limiter.limit(...) decorator"
        )

    @pytest.mark.parametrize("endpoint", [login, refresh, logout, change_password])
    def test_sensitive_auth_endpoint_uses_login_rate_limit(self, endpoint):
        assert "rate_limit_login" in _src(endpoint), (
            f"{endpoint.__name__} must use get_settings().rate_limit_login"
        )


class TestLimiterImportHardening:
    def test_missing_slowapi_fails_fast_in_strict_environment(self, monkeypatch):
        original_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "slowapi" or name.startswith("slowapi."):
                raise ModuleNotFoundError("No module named 'slowapi'")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setattr(builtins, "__import__", _fake_import)
        sys.modules.pop("app.core.limiter", None)

        with pytest.raises(RuntimeError, match=r"Startup validation failed \[rate_limiter\]"):
            importlib.import_module("app.core.limiter")

        sys.modules.pop("app.core.limiter", None)
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setattr(builtins, "__import__", original_import)
        importlib.import_module("app.core.limiter")

    def test_missing_slowapi_only_disables_limiter_in_development(self, monkeypatch):
        original_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "slowapi" or name.startswith("slowapi."):
                raise ModuleNotFoundError("No module named 'slowapi'")
            return original_import(name, globals, locals, fromlist, level)

        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setattr(builtins, "__import__", _fake_import)
        sys.modules.pop("app.core.limiter", None)

        module = importlib.import_module("app.core.limiter")

        assert hasattr(module, "limiter")
        assert callable(module.limiter.limit)

        sys.modules.pop("app.core.limiter", None)
        monkeypatch.setattr(builtins, "__import__", original_import)
        importlib.import_module("app.core.limiter")


class TestAuthAbuseLogging:
    @pytest.mark.asyncio
    async def test_change_password_invalid_current_password_logs_without_secret_leak(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        current_user = _current_user()
        service = AsyncMock(spec=AuthService)
        service.login = AsyncMock(return_value=None)

        with patch("app.api.routes.auth.logger.warning") as mock_warning:
            with pytest.raises(HTTPException) as exc_info:
                await change_password(
                    request=request,
                    payload=ChangePasswordRequest(
                        currentPassword="WrongPassword99!",
                        newPassword="NewSecurePass99!",
                    ),
                    current_user=current_user,
                    service=service,
                )

        assert exc_info.value.status_code == 401
        mock_warning.assert_called_once()
        assert "WrongPassword99!" not in repr(mock_warning.call_args)
        assert "NewSecurePass99!" not in repr(mock_warning.call_args)

    @pytest.mark.asyncio
    async def test_change_password_success_logs_without_secret_leak(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        current_user = _current_user()
        user = MagicMock()
        user.password_hash = "old-hash"
        user.tokens_valid_after = None

        service = AsyncMock(spec=AuthService)
        service.login = AsyncMock(return_value=object())
        service.session = MagicMock()
        service.session.get = AsyncMock(return_value=user)
        service.session.commit = AsyncMock()

        with patch("app.api.routes.auth.logger.info") as mock_info:
            response = await change_password(
                request=request,
                payload=ChangePasswordRequest(
                    currentPassword="CurrentPass99!",
                    newPassword="BrandNewPass99!",
                ),
                current_user=current_user,
                service=service,
            )

        assert response.message == "Password changed."
        mock_info.assert_called_once()
        assert "CurrentPass99!" not in repr(mock_info.call_args)
        assert "BrandNewPass99!" not in repr(mock_info.call_args)

    @pytest.mark.asyncio
    async def test_logout_route_log_still_omits_token_values(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        service = AsyncMock(spec=AuthService)
        service.revoke_token = AsyncMock(side_effect=[False, True])

        with patch("app.api.routes.auth.logger.info") as mock_info:
            response = await logout(
                request=request,
                payload=LogoutRequest(refreshToken="refresh-secret-token"),
                authorization="Bearer access-secret-token",
                service=service,
            )

        assert response.message == "Logged out."
        assert "refresh-secret-token" not in repr(mock_info.call_args)
        assert "access-secret-token" not in repr(mock_info.call_args)
