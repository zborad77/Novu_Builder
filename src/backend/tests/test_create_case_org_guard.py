"""
Create-case organization guard tests.

Verify that POST /cases never creates a project with organization_id=None,
and that super-admins without an explicit org context are rejected.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.schemas.project import ProjectCreate


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(*, is_superadmin: bool, org_id: str | None) -> MagicMock:
    u = MagicMock()
    u.id = "usr_test"
    u.isSuperAdmin = is_superadmin
    u.organizationId = org_id
    u.impersonatedBy = None
    return u


def _make_payload(title: str = "Test Case") -> ProjectCreate:
    return ProjectCreate(title=title)


def _make_created_project():
    p = MagicMock()
    p.id = "prj_new"
    p.status = "draft"
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateCaseOrgGuard:

    @pytest.mark.asyncio
    async def test_tenant_user_creates_case_in_own_org(self):
        """Regular user with an org creates the case; service receives their org_id."""
        from app.api.routes.cases import create_case
        from app.services.project_service import ProjectService

        user = _make_user(is_superadmin=False, org_id="org_abc")
        payload = _make_payload()

        mock_service = AsyncMock(spec=ProjectService)
        mock_service.create_project = AsyncMock(return_value=_make_created_project())

        result = await create_case(
            payload=payload,
            service=mock_service,
            current_user=user,
        )

        assert result.id == "prj_new"
        mock_service.create_project.assert_called_once()
        _, call_kwargs = mock_service.create_project.call_args
        assert call_kwargs["organization_id"] == "org_abc"
        assert call_kwargs["organization_id"] is not None

    @pytest.mark.asyncio
    async def test_superadmin_without_org_is_rejected(self):
        """Superadmin with organizationId=None must receive HTTP 403."""
        from app.api.routes.cases import create_case
        from app.services.project_service import ProjectService

        user = _make_user(is_superadmin=True, org_id=None)
        payload = _make_payload()

        mock_service = AsyncMock(spec=ProjectService)

        with pytest.raises(HTTPException) as exc_info:
            await create_case(
                payload=payload,
                service=mock_service,
                current_user=user,
            )

        assert exc_info.value.status_code == 403
        mock_service.create_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_superadmin_without_org_is_rejected(self):
        """Regular user with no organization assigned must receive HTTP 403."""
        from app.api.routes.cases import create_case
        from app.services.project_service import ProjectService

        user = _make_user(is_superadmin=False, org_id=None)
        payload = _make_payload()

        mock_service = AsyncMock(spec=ProjectService)

        with pytest.raises(HTTPException) as exc_info:
            await create_case(
                payload=payload,
                service=mock_service,
                current_user=user,
            )

        assert exc_info.value.status_code == 403
        mock_service.create_project.assert_not_called()

    @pytest.mark.asyncio
    async def test_organization_id_none_never_reaches_service(self):
        """Service.create_project is never called with organization_id=None."""
        from app.api.routes.cases import create_case
        from app.services.project_service import ProjectService

        for user in [
            _make_user(is_superadmin=True, org_id=None),
            _make_user(is_superadmin=False, org_id=None),
        ]:
            mock_service = AsyncMock(spec=ProjectService)

            with pytest.raises(HTTPException):
                await create_case(
                    payload=_make_payload(),
                    service=mock_service,
                    current_user=user,
                )

            # The guard must fire before any service call
            for call in mock_service.create_project.call_args_list:
                _, kwargs = call
                assert kwargs.get("organization_id") is not None, (
                    "create_project must never be called with organization_id=None"
                )
