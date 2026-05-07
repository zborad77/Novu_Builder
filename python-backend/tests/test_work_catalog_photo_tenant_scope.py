"""Regression: WorkCatalogRepository.get_project_photo_in_project tenant scope.

Before the fix, ProjectPhoto had no organization_id column.
The query filtered on a non-existent attribute (silenced by # type: ignore[attr-defined])
which would raise AttributeError at runtime.

After the fix the repository JOINs through Project to enforce org scope.
These tests verify:
  1. Returns the photo when org matches.
  2. Returns None when org does not match (cross-tenant leak prevention).
  3. Returns None when project_id does not match (even within the same org).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ProjectPhoto
from app.repositories.work_catalog_repository import WorkCatalogRepository


# ─── helpers ─────────────────────────────────────────────────────────────────

def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


async def _create_project(session: AsyncSession, *, org_id: str) -> Project:
    project = Project(
        id=_uid("prj_scope_"),
        organization_id=org_id,
        created_by_user_id="usr_e2e_a1",
        title="Photo tenant scope test project",
        status="draft",
        source="mobile",
    )
    session.add(project)
    await session.commit()
    return project


async def _create_photo(session: AsyncSession, *, project_id: str) -> ProjectPhoto:
    photo = ProjectPhoto(
        id=_uid("ph_scope_"),
        project_id=project_id,
        storage_key=f"uploads/scope_test_{_uid()}.jpg",
        original_filename="scope_test.jpg",
        mime_type="image/jpeg",
        status="active",
        processing_status="ready",
    )
    session.add(photo)
    await session.commit()
    return photo


# ─── tests ───────────────────────────────────────────────────────────────────

class TestGetProjectPhotoInProjectTenantScope:
    """Photo lookup is tenant-scoped via Project.organization_id JOIN."""

    @pytest.mark.asyncio
    async def test_returns_photo_for_correct_org(self, db_session, test_tenants):
        """Owner org can retrieve the photo."""
        project = await _create_project(db_session, org_id=test_tenants["org_a"])
        photo = await _create_photo(db_session, project_id=project.id)

        repo = WorkCatalogRepository(db_session)
        result = await repo.get_project_photo_in_project(
            project.id,
            photo.id,
            organization_id=test_tenants["org_a"],
        )

        assert result is not None
        assert result.id == photo.id

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_org(self, db_session, test_tenants):
        """Cross-tenant request returns None — not the photo, not a 500."""
        project = await _create_project(db_session, org_id=test_tenants["org_a"])
        photo = await _create_photo(db_session, project_id=project.id)

        repo = WorkCatalogRepository(db_session)
        result = await repo.get_project_photo_in_project(
            project.id,
            photo.id,
            organization_id=test_tenants["org_b"],
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_project_same_org(self, db_session, test_tenants):
        """Photo belongs to a different project in the same org — still None."""
        project_a = await _create_project(db_session, org_id=test_tenants["org_a"])
        project_b = await _create_project(db_session, org_id=test_tenants["org_a"])
        photo = await _create_photo(db_session, project_id=project_a.id)

        repo = WorkCatalogRepository(db_session)
        result = await repo.get_project_photo_in_project(
            project_b.id,
            photo.id,
            organization_id=test_tenants["org_a"],
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_photo(self, db_session, test_tenants):
        """Non-existent photo ID returns None without error."""
        project = await _create_project(db_session, org_id=test_tenants["org_a"])

        repo = WorkCatalogRepository(db_session)
        result = await repo.get_project_photo_in_project(
            project.id,
            "ph_does_not_exist",
            organization_id=test_tenants["org_a"],
        )

        assert result is None
