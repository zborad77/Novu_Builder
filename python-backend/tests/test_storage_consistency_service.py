from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.models import Project, ProjectExport, ProjectPhoto
from app.repositories.storage_consistency_repository import StorageConsistencyRepository
from app.services import storage_consistency_service as storage_consistency_mod
from app.services.storage_consistency_service import StorageConsistencyService


async def _seed_storage_consistency_rows(db_session, test_tenants):
    await db_session.execute(delete(ProjectExport))
    await db_session.execute(delete(ProjectPhoto))
    await db_session.execute(delete(Project))
    await db_session.commit()
    token = uuid4().hex[:8]
    base = datetime.now(UTC) + timedelta(days=30)
    project_id = f"prj_cons_{token}"
    photo_id = f"pho_cons_{token}"
    export_id = f"exp_consistency_{token}"

    db_session.add(
        Project(
            id=project_id,
            organization_id=test_tenants["org_a"],
            created_by_user_id="usr_e2e_a1",
            title=f"Storage consistency {token}",
            description="",
            status="draft",
            source="mobile",
            created_at=base,
            updated_at=base,
        )
    )
    db_session.add(
        ProjectPhoto(
            id=photo_id,
            project_id=project_id,
            storage_key=f"projects/{project_id}/original.jpg",
            preview_storage_key=f"projects/{project_id}/preview/original.jpg",
            ai_input_storage_key=f"projects/{project_id}/ai/original.jpg",
            original_filename="original.jpg",
            mime_type="image/jpeg",
            file_size=128,
            processing_status="ready",
            is_primary=True,
            is_analysis_reference=True,
            sort_order=1,
            created_at=base + timedelta(seconds=1),
        )
    )
    db_session.add(
        ProjectExport(
            id=export_id,
            project_id=project_id,
            export_type="quote-pdf",
            status="completed",
            file_name="report.pdf",
            storage_key=f"exports/{project_id}/{export_id}-report.pdf",
            created_at=base + timedelta(seconds=2),
            completed_at=base + timedelta(seconds=2),
            expires_at=base + timedelta(days=7),
        )
    )
    await db_session.commit()
    return {
        "project_id": project_id,
        "photo_id": photo_id,
        "original_key": f"projects/{project_id}/original.jpg",
        "preview_key": f"projects/{project_id}/preview/original.jpg",
        "ai_key": f"projects/{project_id}/ai/original.jpg",
        "orphan_key": f"projects/{project_id}/orphan.jpg",
        "export_id": export_id,
        "export_file_key": f"exports/{project_id}/{export_id}-report.pdf",
    }


@pytest.mark.asyncio
async def test_scan_db_vs_s3_finds_missing_db_objects_and_orphan_storage(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    async def fake_list_storage_keys(*, prefix: str | None = None) -> list[str]:
        if prefix == "projects":
            return [
                seeded["original_key"],
                seeded["preview_key"],
                seeded["orphan_key"],
            ]
        if prefix == "exports":
            return [seeded["export_file_key"]]
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_keys", fake_list_storage_keys)

    result = await service.scan_db_vs_s3()

    assert [issue.key for issue in result.missing_storage_objects] == [seeded["ai_key"]]
    assert result.missing_storage_objects[0].org_id == test_tenants["org_a"]
    assert result.missing_storage_objects[0].source == "db.project_photo.ai_input"

    assert [issue.key for issue in result.orphan_storage_objects] == [seeded["orphan_key"]]
    assert result.orphan_storage_objects[0].org_id == test_tenants["org_a"]
    assert seeded["export_file_key"] not in {issue.key for issue in result.orphan_storage_objects}


@pytest.mark.asyncio
async def test_orphan_detection(monkeypatch, db_session, test_tenants):
    """Storage consistency scan must detect both missing DB-backed objects and orphan keys."""
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    async def fake_list_storage_keys(*, prefix: str | None = None) -> list[str]:
        if prefix == "projects":
            return [
                seeded["original_key"],
                seeded["preview_key"],
                seeded["orphan_key"],
            ]
        if prefix == "exports":
            return [seeded["export_file_key"]]
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_keys", fake_list_storage_keys)

    result = await service.scan_db_vs_s3()

    missing_keys = {issue.key for issue in result.missing_storage_objects}
    orphan_keys = {issue.key for issue in result.orphan_storage_objects}

    assert seeded["ai_key"] in missing_keys
    assert seeded["orphan_key"] in orphan_keys
    assert seeded["export_file_key"] not in orphan_keys


@pytest.mark.asyncio
async def test_scan_db_vs_s3_flags_missing_export_artifact_from_db(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    async def fake_list_storage_keys(*, prefix: str | None = None) -> list[str]:
        if prefix == "projects":
            return [seeded["original_key"], seeded["preview_key"], seeded["ai_key"]]
        if prefix == "exports":
            return []
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_keys", fake_list_storage_keys)

    result = await service.scan_db_vs_s3()

    assert [issue.key for issue in result.missing_storage_objects] == [seeded["export_file_key"]]
    assert result.missing_storage_objects[0].source == "db.project_export.storage"


@pytest.mark.asyncio
async def test_cleanup_orphans_safe_mode_logs_without_deleting(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    scan_result = storage_consistency_mod.StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[
            storage_consistency_mod.StorageConsistencyIssue(
                org_id=test_tenants["org_a"],
                key=seeded["orphan_key"],
                action="orphan_storage_object",
                source="storage.scan",
                project_id=seeded["project_id"],
            )
        ],
    )
    mock_logger = MagicMock()
    mock_delete = AsyncMock()

    monkeypatch.setattr(service, "scan_db_vs_s3", AsyncMock(return_value=scan_result))
    monkeypatch.setattr(storage_consistency_mod, "delete_storage_file", mock_delete)
    monkeypatch.setattr(storage_consistency_mod, "logger", mock_logger)

    actions = await service.cleanup_orphans(safe_mode=True)

    assert actions == [
        storage_consistency_mod.StorageCleanupAction(
            org_id=test_tenants["org_a"],
            key=seeded["orphan_key"],
            action="delete_skipped_safe_mode",
        )
    ]
    mock_delete.assert_not_awaited()
    mock_logger.info.assert_called_once_with(
        "storage.consistency.cleanup",
        org_id=test_tenants["org_a"],
        key=seeded["orphan_key"],
        action="delete_skipped_safe_mode",
    )


@pytest.mark.asyncio
async def test_cleanup_orphans_deletes_when_safe_mode_disabled(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    scan_result = storage_consistency_mod.StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[
            storage_consistency_mod.StorageConsistencyIssue(
                org_id=test_tenants["org_a"],
                key=seeded["orphan_key"],
                action="orphan_storage_object",
                source="storage.scan",
                project_id=seeded["project_id"],
            )
        ],
    )
    mock_logger = MagicMock()
    mock_delete = AsyncMock()

    monkeypatch.setattr(service, "scan_db_vs_s3", AsyncMock(return_value=scan_result))
    monkeypatch.setattr(storage_consistency_mod, "delete_storage_file", mock_delete)
    monkeypatch.setattr(storage_consistency_mod, "logger", mock_logger)

    actions = await service.cleanup_orphans(safe_mode=False)

    assert actions == [
        storage_consistency_mod.StorageCleanupAction(
            org_id=test_tenants["org_a"],
            key=seeded["orphan_key"],
            action="delete_orphan_storage_object",
        )
    ]
    mock_delete.assert_awaited_once_with(relative_storage_key=seeded["orphan_key"])
    mock_logger.info.assert_called_once_with(
        "storage.consistency.cleanup",
        org_id=test_tenants["org_a"],
        key=seeded["orphan_key"],
        action="delete_orphan_storage_object",
    )
