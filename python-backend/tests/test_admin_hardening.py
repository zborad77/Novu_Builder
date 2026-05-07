"""
Admin route hardening tests.

Coverage:
1. All admin routes require superadmin (source / dependency check)
2. admin_retry_job passes organization_id=None explicitly (superadmin bypass)
3. Audit logs are written for write operations (source check)
4. list_users passes org_id filter to the service (functional test)
5. patch_user audit log never includes the password field
6. Impersonated tokens are blocked from admin routes (require_superadmin)
7. execute_job/retry_job bypass requires explicit is_superadmin_context=True
"""
import inspect
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest


def _mock_request() -> StarletteRequest:
    """Minimal Starlette Request for direct handler calls (bypasses slowapi key lookup)."""
    return StarletteRequest({"type": "http", "method": "GET", "path": "/", "headers": []})

import app.api.routes.admin as admin_module
from app.api.deps import ADMIN_CAPABILITIES, require_admin_capability, require_superadmin
from app.api.routes.admin import (
    admin_retry_job,
    create_company,
    create_user,
    list_users,
    patch_company,
    patch_user,
)
from app.api.deps import require_superadmin


# ── Helper ─────────────────────────────────────────────────────────────────────

def _source(fn) -> str:
    return inspect.getsource(fn)


def _has_admin_access_dep(endpoint) -> bool:
    """Return True if endpoint directly depends on require_superadmin OR
    on any require_admin_capability dependency.

    C8: require_admin_capability no longer wraps require_superadmin; it performs
    the superadmin check inline (isSuperAdmin) and falls back to a DB permission
    lookup. We accept either pattern.
    """
    sig = inspect.signature(endpoint)
    for param in sig.parameters.values():
        dep = getattr(param.default, "dependency", None)
        if dep is None:
            continue
        if dep is require_superadmin:
            return True
        # require_admin_capability returns a closure whose name starts with require_admin_
        name = getattr(dep, "__name__", "")
        if name.startswith("require_admin_") or name.startswith("require_"):
            try:
                src = inspect.getsource(dep)
                # Accept old pattern (wraps require_superadmin) or C8 pattern (direct isSuperAdmin check)
                if "require_superadmin" in src or "isSuperAdmin" in src:
                    return True
            except (TypeError, OSError):
                pass
    return False


# ── 1. All admin write routes require superadmin (directly or via capability) ──

class TestAdminRoutesRequireSuperadmin:

    _write_routes = [
        create_company,
        patch_company,
        create_user,
        patch_user,
        admin_retry_job,
    ]

    _read_routes = [
        list_users,
    ]

    @pytest.mark.parametrize("endpoint", _write_routes)
    def test_write_route_has_admin_access_dependency(self, endpoint):
        """Route must depend on require_superadmin or a require_admin_capability wrapper."""
        assert _has_admin_access_dep(endpoint), (
            f"{endpoint.__name__} must depend on require_superadmin or require_admin_capability"
        )

    @pytest.mark.parametrize("endpoint", _read_routes)
    def test_read_route_depends_on_require_superadmin(self, endpoint):
        sig = inspect.signature(endpoint)
        found = any(
            getattr(param.default, "dependency", None) is require_superadmin
            for param in sig.parameters.values()
        )
        assert found, (
            f"{endpoint.__name__} must depend on require_superadmin"
        )


# ── 2. admin_retry_job superadmin bypass ────────────────────────────────────────

class TestAdminRetryJobSuperadminBypass:

    def test_retry_job_called_with_org_id_none(self):
        src = _source(admin_retry_job)
        # Must explicitly pass organization_id=None (not omit it)
        assert "organization_id=None" in src

    def test_execute_job_scheduled_with_org_id_none(self):
        src = _source(admin_retry_job)
        # R-19: enqueue_analysis_job must forward organization_id=None (superadmin path)
        assert "enqueue_analysis_job" in src
        assert "organization_id=None" in src

    def test_no_400_guard_for_missing_org(self):
        src = _source(admin_retry_job)
        # The old (broken) 400 guard must not be present
        assert "status_code=400" not in src


# ── 3. Audit log coverage for write operations ──────────────────────────────────

class TestAdminWriteAuditLogs:

    def test_create_company_writes_audit_log(self):
        src = _source(create_company)
        assert "admin.company.create" in src
        assert "write_audit_log(" in src

    def test_patch_company_writes_audit_log(self):
        src = _source(patch_company)
        assert "admin.company.patch" in src
        assert "write_audit_log(" in src

    def test_create_user_writes_audit_log(self):
        src = _source(create_user)
        assert "admin.user.create" in src
        assert "write_audit_log(" in src

    def test_patch_user_writes_audit_log(self):
        src = _source(patch_user)
        assert "admin.user.patch" in src
        assert "write_audit_log(" in src

    def test_admin_retry_job_writes_audit_log(self):
        src = _source(admin_retry_job)
        assert "admin.job.retry" in src
        assert "write_audit_log(" in src

    def test_patch_user_excludes_password_from_audit(self):
        src = _source(patch_user)
        # Password must be excluded from the audit detail
        assert 'exclude={"password"}' in src or "exclude={'password'}" in src

    def test_create_user_audit_includes_target_org(self):
        src = _source(create_user)
        # Audit detail should carry the target org for traceability
        assert "target_org" in src


# ── 4. list_users passes org_id filter ─────────────────────────────────────────

class TestListUsersOrgFilter:

    def test_list_users_passes_org_id_to_service_source(self):
        src = _source(list_users)
        # org_id query param must be forwarded to service
        assert "organization_id=org_id" in src

    @pytest.mark.asyncio
    async def test_list_users_filters_by_org_id(self):
        mock_service = MagicMock()
        mock_service.list_users = AsyncMock(return_value=([], 0))

        result = await list_users(request=_mock_request(), org_id="org-abc", limit=100, offset=0, service=mock_service, _=MagicMock())

        mock_service.list_users.assert_called_once_with(
            organization_id="org-abc",
            limit=100,
            offset=0,
        )
        assert result.total == 0
        assert result.limit == 100
        assert result.offset == 0
        assert result.hasMore is False

    @pytest.mark.asyncio
    async def test_list_users_no_org_id_passes_none(self):
        mock_service = MagicMock()
        mock_service.list_users = AsyncMock(return_value=([], 0))

        result = await list_users(request=_mock_request(), org_id=None, limit=100, offset=25, service=mock_service, _=MagicMock())

        mock_service.list_users.assert_called_once_with(
            organization_id=None,
            limit=100,
            offset=25,
        )
        assert result.total == 0
        assert result.limit == 100
        assert result.offset == 25
        assert result.hasMore is False


# ── 5. Impersonated token blocked from admin routes ─────────────────────────────

class TestImpersonatedTokenBlocked:

    @pytest.mark.asyncio
    async def test_require_superadmin_blocks_impersonated_token(self):
        """A token with impersonated_by set must be rejected even if user is superadmin."""
        from app.api.deps import require_superadmin
        from app.schemas.auth import AuthUserRead

        impersonated_superadmin = AuthUserRead(
            id="admin-1",
            email="admin@example.com",
            fullName="Admin",
            role="superadmin",
            isActive=True,
            organizationId="org-1",
            isSuperAdmin=True,
            impersonatedBy="other-admin-id",  # token was issued via impersonate
        )
        with pytest.raises(HTTPException) as exc_info:
            await require_superadmin(current_user=impersonated_superadmin)

        assert exc_info.value.status_code == 403
        assert "Impersonated" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_superadmin_allows_real_superadmin(self):
        """A normal superadmin token (no impersonation) passes through."""
        from app.api.deps import require_superadmin
        from app.schemas.auth import AuthUserRead

        real_superadmin = AuthUserRead(
            id="admin-1",
            email="admin@example.com",
            fullName="Admin",
            role="superadmin",
            isActive=True,
            organizationId="org-1",
            isSuperAdmin=True,
            impersonatedBy=None,
        )
        result = await require_superadmin(current_user=real_superadmin)
        assert result.id == "admin-1"

    def test_auth_user_read_has_impersonated_by_field(self):
        """AuthUserRead schema carries impersonatedBy for downstream checks."""
        from app.schemas.auth import AuthUserRead
        import inspect
        src = inspect.getsource(AuthUserRead)
        assert "impersonatedBy" in src

    def test_get_user_by_token_propagates_impersonated_by(self):
        """auth_service.get_user_by_token sets impersonatedBy from JWT payload."""
        from app.services.auth_service import AuthService
        src = inspect.getsource(AuthService.get_user_by_token)
        assert "impersonated_by" in src
        assert "impersonatedBy" in src


# ── 6. Superadmin bypass requires explicit flag ─────────────────────────────────

class TestSuperadminBypassExplicitFlag:

    def test_execute_job_has_is_superadmin_context_param(self):
        """execute_job signature contains the explicit bypass flag."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        assert "is_superadmin_context" in src

    def test_retry_job_has_is_superadmin_context_param(self):
        """retry_job signature contains the explicit bypass flag."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.retry_job)
        assert "is_superadmin_context" in src

    def test_admin_retry_job_passes_true_flag(self):
        """admin_retry_job passes is_superadmin_context=True to both service calls."""
        from app.api.routes.admin import admin_retry_job
        src = inspect.getsource(admin_retry_job)
        assert "is_superadmin_context=True" in src

    def test_analysis_route_passes_flag_based_on_user_role(self):
        """Non-admin routes forward is_superadmin_context from current_user.isSuperAdmin."""
        from app.api.routes.analysis_jobs import create_analysis_job
        src = inspect.getsource(create_analysis_job)
        assert "is_superadmin_context" in src
        assert "isSuperAdmin" in src

    def test_execute_job_guard_fires_without_flag(self):
        """Calling execute_job with org_id=None and no flag raises 403 immediately."""
        from app.services.analysis_service import AnalysisService
        src = inspect.getsource(AnalysisService.execute_job)
        assert "organization_id is None and not is_superadmin_context" in src
        assert "status_code=403" in src


# ── 7. Admin password reset invalidates existing tokens (R-SEC-08) ──────────────

class TestAdminPasswordResetInvalidatesTokens:
    """After an admin-forced password reset, all pre-existing tokens must be rejected."""

    def test_reset_password_sets_tokens_valid_after_in_source(self):
        """reset_user_password must call the shared global invalidation helper."""
        from app.api.routes.admin import reset_user_password
        src = inspect.getsource(reset_user_password)
        assert "invalidate_user_token_state" in src, (
            "reset_user_password must invalidate the target user's global token state"
        )

    def test_reset_password_commits_after_invalidation(self):
        """The audited commit path must follow the shared invalidation helper."""
        from app.api.routes.admin import reset_user_password
        src = inspect.getsource(reset_user_password)
        invalidation_pos = src.find("invalidate_user_token_state")
        commit_pos = src.find("commit_security_critical_audit(", invalidation_pos)
        assert invalidation_pos != -1 and commit_pos != -1, (
            "Security-audited commit path must appear after global invalidation setup"
        )

    @pytest.mark.asyncio
    async def test_reset_password_writes_tokens_valid_after_on_user(self):
        """Functional: reset_user_password updates both tva and token_version."""
        from datetime import UTC, datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from fastapi import Request

        from app.api.routes.admin import ResetPasswordPayload, reset_user_password
        from app.schemas.auth import AuthUserRead

        # Minimal User mock with a mutable tokens_valid_after attribute
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.email = "user@test.com"
        mock_user.organization_id = "org-1"
        mock_user.tokens_valid_after = None
        mock_user.token_version = 0

        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=mock_user)
        mock_session.commit = AsyncMock()

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        # Strip microseconds to match .replace(microsecond=0) in the implementation
        before = datetime.now(UTC).replace(microsecond=0)

        with patch("app.api.routes.admin.commit_security_critical_audit", new_callable=AsyncMock):
            with patch("app.api.routes.admin.TokenRepository.revoke_all_user_sessions", new=AsyncMock(return_value=[])):
                with patch("app.api.routes.admin.logger"):
                    await reset_user_password(
                        request=mock_request,
                        user_id="user-1",
                        payload=ResetPasswordPayload(password="NewSecure@Pass1"),
                        current_user=mock_current_user,
                        session=mock_session,
                        auth_redis=None,
                    )

        after = datetime.now(UTC).replace(microsecond=0)

        assert mock_user.tokens_valid_after is not None, (
            "tokens_valid_after must be set after admin password reset"
        )
        assert mock_user.tokens_valid_after.microsecond == 0, (
            "tokens_valid_after must have microseconds stripped (consistent DB precision)"
        )
        assert before <= mock_user.tokens_valid_after <= after, (
            "tokens_valid_after must be a current timestamp"
        )
        assert mock_user.token_version == 1, "token_version must bump on admin password reset"

    @pytest.mark.asyncio
    async def test_reset_password_succeeds_when_token_state_cache_cannot_be_updated(self):
        from datetime import UTC, datetime, timedelta

        from fastapi import Request

        from app.api.routes.admin import ResetPasswordPayload, reset_user_password
        from app.repositories.token_repository import SessionTokenRevocation
        from app.schemas.auth import AuthUserRead

        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.email = "user@test.com"
        mock_user.organization_id = "org-1"
        mock_user.tokens_valid_after = None
        mock_user.token_version = 0

        mock_session = MagicMock()
        mock_session.get = AsyncMock(return_value=mock_user)
        mock_session.commit = AsyncMock()

        mock_current_user = AuthUserRead(
            id="sa-1",
            email="sa@test.com",
            fullName="SA",
            role="superadmin",
            isActive=True,
            organizationId="org-1",
            isSuperAdmin=True,
            impersonatedBy=None,
        )

        mock_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/admin/users/user-1/reset-password",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "app": MagicMock(),
            }
        )
        mock_request.app.state.auth_token_store = object()

        revocations = [
            SessionTokenRevocation(
                jti="jti-1",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        ]

        with (
            patch("app.api.routes.admin.commit_security_critical_audit", new_callable=AsyncMock),
            patch("app.api.routes.admin.TokenRepository.revoke_all_user_sessions", new=AsyncMock(return_value=revocations)),
            patch(
                "app.api.routes.admin.TokenRepository.cache_revoked_token",
                new=AsyncMock(return_value=False),
            ),
        ):
            await reset_user_password(
                request=mock_request,
                user_id="user-1",
                payload=ResetPasswordPayload(password="NewSecure@Pass1"),
                current_user=mock_current_user,
                session=mock_session,
                auth_redis=object(),
            )


class TestAuditMiddlewareDedup:
    """Middleware must not produce duplicate audit rows for routes that call write_audit_log() directly."""

    def test_forgot_password_is_in_skip_paths(self):
        from app.core.audit import _SKIP_PATHS
        assert "/api/v1/auth/forgot-password" in _SKIP_PATHS, (
            "forgot-password is unauthenticated — middleware would log user_id=None; "
            "explicit write_audit_log() inside the route carries the real user_id"
        )

    def test_reset_password_is_in_skip_paths(self):
        from app.core.audit import _SKIP_PATHS
        assert "/api/v1/auth/reset-password" in _SKIP_PATHS, (
            "reset-password is unauthenticated — middleware would log user_id=None; "
            "explicit write_audit_log() inside the route carries the real user_id"
        )

    def test_admin_prefix_is_skipped(self):
        from app.core.audit import _SKIP_PREFIXES
        assert any(p == "/api/v1/admin" for p in _SKIP_PREFIXES), (
            "admin routes use explicit write_audit_log() with business detail — middleware must not double-log"
        )
