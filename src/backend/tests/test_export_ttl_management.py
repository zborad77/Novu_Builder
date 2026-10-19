from datetime import UTC, datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

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


async def _create_pending_export(
    service: ExportService,
    *,
    project_id: str,
    export_type: str,
    file_name: str,
) -> ProjectExport:
    return await service._create_pending_export_record(
        export_id=f"exp_{uuid4().hex[:8]}",
        project_id=project_id,
        export_type=export_type,
        file_name=file_name,
        created_at=datetime.now(UTC),
    )


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
    assert row.status == "failed"
    assert row.storage_key == export.storageKey
    assert export.status == "failed"
    assert export.expiresAt is not None
    assert before + timedelta(days=7) <= _as_utc(row.expires_at) <= after + timedelta(days=7, seconds=1)


@pytest.mark.asyncio
async def test_quote_pdf_export_fails_closed_when_artifact_is_missing(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "Quote PDF"
    case_detail.finalProposal = MagicMock(subject="Nabidka")

    monkeypatch.setattr(export_service_mod, "write_storage_file", AsyncMock(return_value=None))
    monkeypatch.setattr(export_service_mod, "storage_key_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(export_service_mod, "delete_storage_file", AsyncMock(return_value=None))
    monkeypatch.setattr(export_service_mod, "_build_pdf_bytes", lambda _detail: b"pdf-bytes")

    created = await _create_pending_export(
        service,
        project_id=project_id,
        export_type="quote-pdf",
        file_name="nabidka.pdf",
    )
    export = await service.process_export_by_id(created.id, case_detail=case_detail)

    row = await db_session.get(ProjectExport, created.id)
    assert row is not None
    assert row.status == "failed"
    assert row.storage_key is None
    assert row.completed_at is None
    assert export is not None
    assert export.status == "failed"


@pytest.mark.asyncio
async def test_quote_pdf_export_records_completed_only_after_verified_storage(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "Quote PDF"
    case_detail.finalProposal = MagicMock(subject="Nabidka")

    write_storage = AsyncMock(return_value=None)
    storage_exists = AsyncMock(return_value=True)
    monkeypatch.setattr(export_service_mod, "write_storage_file", write_storage)
    monkeypatch.setattr(export_service_mod, "storage_key_exists", storage_exists)
    monkeypatch.setattr(export_service_mod, "_build_pdf_bytes", lambda _detail: b"pdf-bytes")

    created = await _create_pending_export(
        service,
        project_id=project_id,
        export_type="quote-pdf",
        file_name="nabidka.pdf",
    )
    export = await service.process_export_by_id(created.id, case_detail=case_detail)

    row = await db_session.get(ProjectExport, created.id)
    assert row is not None
    assert row.status == "completed"
    assert row.storage_key is not None
    assert row.completed_at is not None
    assert export is not None
    assert export.status == "completed"
    write_storage.assert_awaited_once()
    storage_exists.assert_awaited_once()


@pytest.mark.asyncio
async def test_case_zip_export_fails_closed_when_any_photo_is_missing(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "ZIP"
    case_detail.model_dump = MagicMock(return_value={"id": project_id})
    case_detail.latestAnalysis = None
    case_detail.photos = [
        {
            "storageKey": f"projects/{project_id}/missing.jpg",
        }
    ]

    monkeypatch.setattr(export_service_mod, "read_storage_file", AsyncMock(return_value=None))
    monkeypatch.setattr(export_service_mod, "delete_storage_file", AsyncMock(return_value=None))

    created = await _create_pending_export(
        service,
        project_id=project_id,
        export_type="case-zip",
        file_name="zip.zip",
    )
    export = await service.process_export_by_id(created.id, case_detail=case_detail)

    row = await db_session.get(ProjectExport, created.id)
    assert row is not None
    assert row.status == "failed"
    assert row.storage_key is None
    assert export is not None
    assert export.status == "failed"


@pytest.mark.asyncio
async def test_export_interruption_marks_generating_export_failed(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "Interrupted"
    case_detail.finalProposal = MagicMock(subject="Nabidka")

    monkeypatch.setattr(export_service_mod, "_build_pdf_bytes", lambda _detail: b"pdf-bytes")
    monkeypatch.setattr(
        export_service_mod,
        "write_storage_file",
        AsyncMock(side_effect=TimeoutError("write interrupted")),
    )
    monkeypatch.setattr(export_service_mod, "delete_storage_file", AsyncMock(return_value=None))

    created = await _create_pending_export(
        service,
        project_id=project_id,
        export_type="quote-pdf",
        file_name="nabidka.pdf",
    )
    export = await service.process_export_by_id(created.id, case_detail=case_detail)

    row = await db_session.get(ProjectExport, created.id)
    assert row is not None
    assert row.status == "failed"
    assert row.storage_key is None
    assert row.completed_at is None
    assert export is not None
    assert export.status == "failed"


@pytest.mark.asyncio
async def test_quote_pdf_export_enqueues_heavy_job_when_lane_enabled(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    work_queue = AsyncMock()
    service = ExportService(ExportRepository(db_session), work_queue=work_queue)
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "Queued Quote PDF"
    case_detail.finalProposal = MagicMock(subject="Nabidka")

    settings = MagicMock()
    settings.export_ttl_days = 7
    settings.worker_heavy_concurrency = 1
    settings.heavy_queue_max_depth = 25
    monkeypatch.setattr(export_service_mod, "get_settings", lambda: settings)
    enqueue = AsyncMock()
    monkeypatch.setattr(export_service_mod, "enqueue_heavy_job", enqueue)
    monkeypatch.setattr(export_service_mod, "write_storage_file", AsyncMock())

    export = await service.create_quote_pdf_export(case_detail=case_detail)

    row = await db_session.get(ProjectExport, export.id)
    assert row is not None
    assert row.status == "pending"
    assert row.storage_key is None
    assert export.status == "pending"
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_export_by_id_completes_pending_export(monkeypatch, db_session, test_tenants):
    project_id = await _seed_project(db_session, test_tenants)
    service = ExportService(ExportRepository(db_session))
    case_detail = MagicMock()
    case_detail.id = project_id
    case_detail.title = "Worker Quote PDF"
    case_detail.finalProposal = MagicMock(subject="Nabidka")

    created = await service._create_pending_export_record(
        export_id=f"exp_{uuid4().hex[:8]}",
        project_id=project_id,
        export_type="quote-pdf",
        file_name="nabidka.pdf",
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(export_service_mod, "_build_pdf_bytes", lambda _detail: b"pdf-bytes")
    monkeypatch.setattr(export_service_mod, "write_storage_file", AsyncMock(return_value=None))
    monkeypatch.setattr(export_service_mod, "storage_key_exists", AsyncMock(return_value=True))

    export = await service.process_export_by_id(created.id, case_detail=case_detail)

    row = await db_session.get(ProjectExport, created.id)
    assert export is not None
    assert row is not None
    assert row.status == "completed"
    assert export.status == "completed"


@pytest.mark.asyncio
async def test_get_export_marks_missing_completed_artifact_as_failed(monkeypatch, db_session, test_tenants):
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
            file_name="missing.pdf",
            storage_key=f"exports/{project_id}/{export_id}-missing.pdf",
            created_at=now,
            completed_at=now,
            expires_at=now + timedelta(days=7),
        )
    )
    await db_session.commit()

    monkeypatch.setattr(export_service_mod, "storage_key_exists", AsyncMock(return_value=False))

    service = ExportService(ExportRepository(db_session))
    export = await service.get_export(export_id, organization_id=test_tenants["org_a"])

    row = await db_session.get(ProjectExport, export_id)
    assert export is not None
    assert export.status == "failed"
    assert export.downloadUrl is None
    assert row is not None
    assert row.status == "failed"
    assert row.storage_key is None
    assert row.completed_at is None


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
    result = await service.get_export(export_id, organization_id=test_tenants["org_a"])

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
