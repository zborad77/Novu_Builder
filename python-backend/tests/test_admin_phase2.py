"""
Admin hardening phase-2 tests.

Coverage:
1. Rate limiting — @limiter.limit applied to all 7 write/sensitive admin routes
2. RBAC foundation — require_admin_capability factory; superadmin passes, others denied
3. Audit enforcement — all 7 write routes call write_audit_log; no password logged
4. /admin/jobs filtering — org_id filter, status filter, limit/cap
5. Impersonation hardening — impersonated token blocked from admin routes (via require_superadmin)
"""
import inspect

import pytest
from fastapi import HTTPException

from app.api.deps import ADMIN_CAPABILITIES, require_admin_capability, require_superadmin
from app.api.routes.admin import (
    admin_retry_job,
    create_company,
    create_user,
    impersonate_user,
    list_all_jobs,
    patch_company,
    patch_user,
    reset_user_password,
)
from app.schemas.auth import AuthUserRead


# ── Helpers ────────────────────────────────────────────────────────────────────

def _src(fn) -> str:
    return inspect.getsource(fn)


def _has_limiter_decorator(fn) -> bool:
    """Check that the function's source contains @limiter.limit(...)."""
    src = _src(fn)
    return "@limiter.limit(" in src


def _superadmin_user(**kwargs) -> AuthUserRead:
    defaults = dict(
        id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
        isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
    )
    defaults.update(kwargs)
    return AuthUserRead(**defaults)


# ── 1. Rate limiting ───────────────────────────────────────────────────────────

class TestRateLimiting:
    """Verify @limiter.limit decorator is present on all sensitive admin routes."""

    _limited_routes = [
        create_company,
        patch_company,
        create_user,
        patch_user,
        reset_user_password,
        admin_retry_job,
        impersonate_user,
    ]

    @pytest.mark.parametrize("endpoint", _limited_routes)
    def test_endpoint_has_limiter_decorator(self, endpoint):
        assert _has_limiter_decorator(endpoint), (
            f"{endpoint.__name__} must have @limiter.limit(...) decorator"
        )

    def test_reset_password_uses_sensitive_limit(self):
        src = _src(reset_user_password)
        assert "rate_limit_admin_sensitive" in src

    def test_impersonate_uses_sensitive_limit(self):
        src = _src(impersonate_user)
        assert "rate_limit_admin_sensitive" in src

    def test_admin_retry_uses_write_limit(self):
        src = _src(admin_retry_job)
        assert "rate_limit_admin_write" in src

    def test_create_company_uses_write_limit(self):
        src = _src(create_company)
        assert "rate_limit_admin_write" in src

    def test_create_user_uses_write_limit(self):
        src = _src(create_user)
        assert "rate_limit_admin_write" in src

    def test_rate_limit_admin_write_config_field_exists(self):
        from app.core.config import Settings
        src = inspect.getsource(Settings)
        assert "rate_limit_admin_write" in src
        assert "rate_limit_admin_sensitive" in src


# ── 2. RBAC foundation ─────────────────────────────────────────────────────────

class TestRBACFoundation:

    def test_admin_capabilities_set_is_defined(self):
        assert isinstance(ADMIN_CAPABILITIES, frozenset)
        assert len(ADMIN_CAPABILITIES) > 0

    def test_admin_capabilities_contains_required_keys(self):
        for cap in ("admin:read", "admin:write", "admin:jobs", "admin:impersonate"):
            assert cap in ADMIN_CAPABILITIES

    def test_require_admin_capability_returns_callable(self):
        dep = require_admin_capability("admin:write")
        assert callable(dep)

    def test_require_admin_capability_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown admin capability"):
            require_admin_capability("admin:unknown")

    def test_capability_dependency_wraps_require_superadmin(self):
        dep = require_admin_capability("admin:write")
        src = inspect.getsource(dep)
        assert "require_superadmin" in src

    @pytest.mark.asyncio
    async def test_capability_dep_allows_superadmin(self):
        dep = require_admin_capability("admin:write")
        user = _superadmin_user()
        result = await dep(current_user=user)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_capability_dep_blocks_impersonated_token(self):
        """Impersonated tokens must be blocked: require_superadmin (called transitively)
        raises 403. We verify via require_superadmin directly, since FastAPI DI is not
        active in unit tests — the transitive call is verified by source inspection."""
        # Source verification: _check depends on require_superadmin
        dep = require_admin_capability("admin:write")
        src = inspect.getsource(dep)
        assert "require_superadmin" in src
        # Functional: require_superadmin (the guard) blocks impersonated tokens
        user = _superadmin_user(impersonatedBy="other-admin-id")
        with pytest.raises(HTTPException) as exc_info:
            await require_superadmin(current_user=user)
        assert exc_info.value.status_code == 403

    def test_admin_jobs_route_uses_jobs_capability(self):
        src = _src(list_all_jobs)
        assert 'require_admin_capability("admin:jobs")' in src

    def test_impersonate_route_uses_impersonate_capability(self):
        src = _src(impersonate_user)
        assert 'require_admin_capability("admin:impersonate")' in src

    def test_write_routes_use_write_capability(self):
        for fn in (create_company, patch_company, create_user, patch_user):
            src = _src(fn)
            assert 'require_admin_capability("admin:write")' in src, (
                f"{fn.__name__} must use admin:write capability"
            )


# ── 3. Audit enforcement ───────────────────────────────────────────────────────

class TestAuditEnforcement:

    _write_routes_with_audit = [
        (create_company, "admin.company.create"),
        (patch_company, "admin.company.patch"),
        (create_user, "admin.user.create"),
        (patch_user, "admin.user.patch"),
        (reset_user_password, "admin.user.reset_password"),
        (admin_retry_job, "admin.job.retry"),
        (impersonate_user, "admin.impersonate"),
    ]

    @pytest.mark.parametrize("endpoint,action", _write_routes_with_audit)
    def test_write_route_calls_write_audit_log(self, endpoint, action):
        src = _src(endpoint)
        assert "write_audit_log(" in src, (
            f"{endpoint.__name__} must call write_audit_log()"
        )
        assert action in src, (
            f"{endpoint.__name__} must log action '{action}'"
        )

    def test_patch_user_excludes_password_from_audit(self):
        src = _src(patch_user)
        assert 'exclude={"password"}' in src or "exclude={'password'}" in src

    def test_reset_password_does_not_log_password_value(self):
        src = _src(reset_user_password)
        # detail dict must not include the password field
        assert '"password"' not in src.split("write_audit_log")[1].split(")")[0]

    def test_impersonate_does_not_log_token(self):
        """The detail dict passed to write_audit_log must not contain the JWT token value."""
        src = _src(impersonate_user)
        # Extract just the detail dict literal inside write_audit_log(...)
        # We look between 'detail={' and the closing '},' of the detail arg
        assert "write_audit_log(" in src
        detail_start = src.index("detail={")
        detail_end = src.index("},", detail_start)
        detail_section = src[detail_start:detail_end]
        # accessToken / token secret must NOT be in the logged detail
        assert "token" not in detail_section.lower()

    def test_audit_write_failure_logs_warning(self):
        """write_audit_log must emit a warning on failure (not silently swallow)."""
        from app.core.audit import write_audit_log
        src = inspect.getsource(write_audit_log)
        assert "SECURITY_EVENT: audit_write_failed" in src
        assert "logger.warning" in src

    def test_impersonate_audit_includes_target_email(self):
        src = _src(impersonate_user)
        assert "impersonated_email" in src


# ── 4. /admin/jobs filtering and pagination ────────────────────────────────────

class TestAdminJobsFiltering:

    def test_list_all_jobs_has_org_id_query_param(self):
        src = _src(list_all_jobs)
        assert "org_id" in src

    def test_list_all_jobs_has_limit_query_param(self):
        src = _src(list_all_jobs)
        assert "limit" in src

    def test_list_all_jobs_has_status_filter(self):
        src = _src(list_all_jobs)
        assert "job_status" in src or "status" in src

    def test_list_all_jobs_limit_default_50(self):
        src = _src(list_all_jobs)
        # default=50 must appear in the limit Query definition
        assert "default=50" in src

    def test_list_all_jobs_limit_max_200(self):
        """Hard cap of 200 must be specified in Query(le=200)."""
        src = _src(list_all_jobs)
        assert "le=200" in src

    def test_list_all_jobs_applies_org_id_filter_in_source(self):
        src = _src(list_all_jobs)
        assert "Project.organization_id == org_id" in src

    def test_list_all_jobs_applies_limit_in_source(self):
        src = _src(list_all_jobs)
        assert ".limit(limit)" in src

    def test_list_all_jobs_ordered_by_created_at(self):
        src = _src(list_all_jobs)
        assert "created_at.desc()" in src

    def test_list_all_jobs_requires_admin_jobs_capability(self):
        src = _src(list_all_jobs)
        assert 'require_admin_capability("admin:jobs")' in src


# ── 5. Impersonation hardening (additional checks) ────────────────────────────

class TestImpersonationHardening:

    def test_impersonate_route_rate_limited(self):
        assert _has_limiter_decorator(impersonate_user)

    def test_impersonate_route_uses_impersonate_capability(self):
        src = _src(impersonate_user)
        assert "admin:impersonate" in src

    def test_impersonate_blocks_superadmin_target(self):
        """Route must reject impersonating another superadmin."""
        src = _src(impersonate_user)
        assert "is_superadmin" in src
        assert "Cannot impersonate" in src

    def test_impersonate_token_carries_impersonated_by_claim(self):
        """JWT payload must include impersonated_by for audit trail."""
        src = _src(impersonate_user)
        assert '"impersonated_by"' in src or "'impersonated_by'" in src

    @pytest.mark.asyncio
    async def test_require_superadmin_blocks_impersonated_admin_token(self):
        """Even if the target user is superadmin, impersonated token is rejected."""
        user = _superadmin_user(impersonatedBy="original-admin-id")
        with pytest.raises(HTTPException) as exc_info:
            await require_superadmin(current_user=user)
        assert exc_info.value.status_code == 403
        assert "Impersonated" in exc_info.value.detail
