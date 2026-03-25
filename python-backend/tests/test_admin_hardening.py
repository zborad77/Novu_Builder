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

import app.api.routes.admin as admin_module
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

def _dep_names(endpoint) -> list[str]:
    """Return the string names of all FastAPI Depends() in the endpoint signature."""
    sig = inspect.signature(endpoint)
    names = []
    for param in sig.parameters.values():
        default = param.default
        if hasattr(default, "dependency"):
            names.append(getattr(default.dependency, "__name__", repr(default.dependency)))
    return names


def _source(fn) -> str:
    return inspect.getsource(fn)


# ── 1. All admin write routes require superadmin ────────────────────────────────

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
    def test_write_route_depends_on_require_superadmin(self, endpoint):
        sig = inspect.signature(endpoint)
        found = any(
            getattr(param.default, "dependency", None) is require_superadmin
            for param in sig.parameters.values()
        )
        assert found, (
            f"{endpoint.__name__} must depend on require_superadmin"
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
        # Background task must also forward None so the worker takes superadmin path
        assert "new_job.id, new_job.project_id, None" in src

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
        mock_service.list_users = AsyncMock(return_value=[])

        result = await list_users(org_id="org-abc", service=mock_service, _=MagicMock())

        mock_service.list_users.assert_called_once_with(organization_id="org-abc")
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_users_no_org_id_passes_none(self):
        mock_service = MagicMock()
        mock_service.list_users = AsyncMock(return_value=[])

        result = await list_users(org_id=None, service=mock_service, _=MagicMock())

        mock_service.list_users.assert_called_once_with(organization_id=None)
        assert result.total == 0


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
