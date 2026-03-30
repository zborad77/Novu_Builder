from datetime import UTC, datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete

from app.models import Project, ProjectExport
from app.repositories.export_repository import ExportRepository
from app.services import export_service as export_service_mod
from app.services.export_service import ExportService


async def _seed_project(db_session, test_tenants) -> str:
    token = uuid4().hex[:8]
    created_at = datetime.now(UTC)
    project_id = f"prj_exp_{token}"
    db_session.add(
        Project(
            id=project_id,
            organization_id=test_tenants["org_a"],
            created_by_user_id="usr_e2e_a1",
            title=f"Export TTL {token}",
            description="",
            status="draft",
            source="mobile",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    await db_session.commit()
    return project_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@pytest.mark.asyncio
async def test_create_export_persists_db_expires_at(db_session, test_tenants):
    await db_session.execute(delete(ProjectExport))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))

    before = datetime.now(UTC)
    export = await service.create_export(case_id=project_id, export_type="report-pdf")
    after = datetime.now(UTC)

    row = await db_session.get(ProjectExport, export.id)
    assert row is not None
    assert row.project_id == project_id
    assert row.storage_key == export.storageKey
    assert export.expiresAt is not None
    assert before + timedelta(days=7) <= _as_utc(row.expires_at) <= after + timedelta(days=7, seconds=1)


@pytest.mark.asyncio
async def test_get_export_rejects_expired_records(db_session, test_tenants):
    await db_session.execute(delete(ProjectExport))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants)
    now = datetime.now(UTC)
    export_id = f"exp_{uuid4().hex[:8]}"
    db_session.add(
        ProjectExport(
            id=export_id,
            project_id=project_id,
            export_type="quote-pdf",
            status="completed",
            file_name="expired.pdf",
            storage_key=f"exports/{project_id}/{export_id}-expired.pdf",
            created_at=now - timedelta(days=8),
            completed_at=now - timedelta(days=8),
            expires_at=now - timedelta(minutes=1),
        )
    )
    await db_session.commit()

    service = ExportService(ExportRepository(db_session))
    result = await service.get_export(export_id)

    assert result is None


@pytest.mark.asyncio
async def test_delete_expired_exports_removes_storage_and_db_row(monkeypatch, db_session, test_tenants):
    await db_session.execute(delete(ProjectExport))
    await db_session.commit()
    project_id = await _seed_project(db_session, test_tenants)
    now = datetime.now(UTC)
    expired_id = f"exp_{uuid4().hex[:8]}"
    fresh_id = f"exp_{uuid4().hex[:8]}"

    db_session.add_all(
        [
            ProjectExport(
                id=expired_id,
                project_id=project_id,
                export_type="quote-pdf",
                status="completed",
                file_name="expired.pdf",
                storage_key=f"exports/{project_id}/{expired_id}-expired.pdf",
                created_at=now - timedelta(days=8),
                completed_at=now - timedelta(days=8),
                expires_at=now - timedelta(minutes=1),
            ),
            ProjectExport(
                id=fresh_id,
                project_id=project_id,
                export_type="quote-docx",
                status="completed",
                file_name="fresh.docx",
                storage_key=f"exports/{project_id}/{fresh_id}-fresh.docx",
                created_at=now,
                completed_at=now,
                expires_at=now + timedelta(days=7),
            ),
        ]
    )
    await db_session.commit()

    delete_storage = AsyncMock()
    monkeypatch.setattr(export_service_mod, "delete_storage_file", delete_storage)

    service = ExportService(ExportRepository(db_session))
    deleted = await service.delete_expired_exports(now=now)

    assert deleted == 1
    delete_storage.assert_awaited_once_with(
        relative_storage_key=f"exports/{project_id}/{expired_id}-expired.pdf"
    )
    assert await db_session.get(ProjectExport, expired_id) is None
    assert await db_session.get(ProjectExport, fresh_id) is not None
