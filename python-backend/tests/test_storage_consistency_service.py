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
    orphan_last_modified = datetime.now(UTC) - timedelta(hours=48)

    async def fake_list_storage_objects(*, prefix: str | None = None) -> list[dict[str, object]]:
        if prefix == "projects":
            return [
                {"key": seeded["original_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["preview_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["orphan_key"], "last_modified_at": orphan_last_modified},
            ]
        if prefix == "exports":
            return [{"key": seeded["export_file_key"], "last_modified_at": datetime.now(UTC)}]
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_objects", fake_list_storage_objects)

    result = await service.scan_db_vs_s3()

    assert [issue.key for issue in result.missing_storage_objects] == [seeded["ai_key"]]
    assert result.missing_storage_objects[0].org_id == test_tenants["org_a"]
    assert result.missing_storage_objects[0].source == "db.project_photo.ai_input"

    assert [issue.key for issue in result.orphan_storage_objects] == [seeded["orphan_key"]]
    assert result.orphan_storage_objects[0].org_id == test_tenants["org_a"]
    assert result.orphan_storage_objects[0].last_modified_at == orphan_last_modified.isoformat()
    assert result.orphan_summary.orphan_count == 1
    assert result.orphan_summary.eligible_delete_count == 1
    assert seeded["export_file_key"] not in {issue.key for issue in result.orphan_storage_objects}


@pytest.mark.asyncio
async def test_orphan_detection(monkeypatch, db_session, test_tenants):
    """Storage consistency scan must detect both missing DB-backed objects and orphan keys."""
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))

    async def fake_list_storage_objects(*, prefix: str | None = None) -> list[dict[str, object]]:
        if prefix == "projects":
            return [
                {"key": seeded["original_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["preview_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["orphan_key"], "last_modified_at": datetime.now(UTC)},
            ]
        if prefix == "exports":
            return [{"key": seeded["export_file_key"], "last_modified_at": datetime.now(UTC)}]
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_objects", fake_list_storage_objects)

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

    async def fake_list_storage_objects(*, prefix: str | None = None) -> list[dict[str, object]]:
        if prefix == "projects":
            return [
                {"key": seeded["original_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["preview_key"], "last_modified_at": datetime.now(UTC)},
                {"key": seeded["ai_key"], "last_modified_at": datetime.now(UTC)},
            ]
        if prefix == "exports":
            return []
        raise AssertionError(f"Unexpected prefix {prefix!r}")

    monkeypatch.setattr(storage_consistency_mod, "list_storage_objects", fake_list_storage_objects)

    result = await service.scan_db_vs_s3()

    assert [issue.key for issue in result.missing_storage_objects] == [seeded["export_file_key"]]
    assert result.missing_storage_objects[0].source == "db.project_export.storage"


@pytest.mark.asyncio
async def test_cleanup_orphans_safe_mode_logs_without_deleting(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))
    now = datetime.now(UTC)

    scan_result = storage_consistency_mod.StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[
            storage_consistency_mod.StorageConsistencyIssue(
                org_id=test_tenants["org_a"],
                key=seeded["orphan_key"],
                action="orphan_storage_object",
                source="storage.scan",
                project_id=seeded["project_id"],
                last_modified_at=now.isoformat(),
                age_seconds=3600,
            )
        ],
        orphan_summary=storage_consistency_mod.StorageOrphanSummary(
            orphan_count=1,
            eligible_delete_count=1,
            retained_count=0,
            minimum_age_seconds=0,
            approval_token="token-1",
        ),
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
            project_id=seeded["project_id"],
            age_seconds=3600,
        )
    ]
    mock_delete.assert_not_awaited()
    mock_logger.info.assert_called_once_with(
        "storage.consistency.cleanup",
        org_id=test_tenants["org_a"],
        key=seeded["orphan_key"],
        action="delete_skipped_safe_mode",
        project_id=seeded["project_id"],
        age_seconds=3600,
        minimum_orphan_age_seconds=0,
    )


@pytest.mark.asyncio
async def test_cleanup_orphans_deletes_when_safe_mode_disabled(monkeypatch, db_session, test_tenants):
    seeded = await _seed_storage_consistency_rows(db_session, test_tenants)
    service = StorageConsistencyService(StorageConsistencyRepository(db_session))
    now = datetime.now(UTC)

    scan_result = storage_consistency_mod.StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[
            storage_consistency_mod.StorageConsistencyIssue(
                org_id=test_tenants["org_a"],
                key=seeded["orphan_key"],
                action="orphan_storage_object",
                source="storage.scan",
                project_id=seeded["project_id"],
                last_modified_at=now.isoformat(),
                age_seconds=48 * 3600,
            )
        ],
        orphan_summary=storage_consistency_mod.StorageOrphanSummary(
            orphan_count=1,
            eligible_delete_count=1,
            retained_count=0,
            minimum_age_seconds=24 * 3600,
            approval_token="token-allow",
        ),
    )
    mock_logger = MagicMock()
    mock_delete = AsyncMock()

    monkeypatch.setattr(service, "scan_db_vs_s3", AsyncMock(return_value=scan_result))
    monkeypatch.setattr(storage_consistency_mod, "delete_storage_file", mock_delete)
    monkeypatch.setattr(storage_consistency_mod, "logger", mock_logger)

    actions = await service.cleanup_orphans(
        safe_mode=False,
        minimum_orphan_age_seconds=24 * 3600,
        approval_token="token-allow",
    )

    assert actions == [
        storage_consistency_mod.StorageCleanupAction(
            org_id=test_tenants["org_a"],
            key=seeded["orphan_key"],
            action="delete_orphan_storage_object",
            project_id=seeded["project_id"],
            age_seconds=48 * 3600,
        )
    ]
    mock_delete.assert_awaited_once_with(relative_storage_key=seeded["orphan_key"])
    mock_logger.info.assert_called_once_with(
        "storage.consistency.cleanup",
        org_id=test_tenants["org_a"],
        key=seeded["orphan_key"],
        action="delete_orphan_storage_object",
        project_id=seeded["project_id"],
        age_seconds=48 * 3600,
        minimum_orphan_age_seconds=24 * 3600,
    )


@pytest.mark.asyncio
async def test_cleanup_orphans_requires_matching_approval_token(monkeypatch, db_session, test_tenants):
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
                age_seconds=96 * 3600,
            )
        ],
        orphan_summary=storage_consistency_mod.StorageOrphanSummary(
            orphan_count=1,
            eligible_delete_count=1,
            retained_count=0,
            minimum_age_seconds=24 * 3600,
            approval_token="token-required",
        ),
    )

    monkeypatch.setattr(service, "scan_db_vs_s3", AsyncMock(return_value=scan_result))
    monkeypatch.setattr(storage_consistency_mod, "delete_storage_file", AsyncMock())

    with pytest.raises(storage_consistency_mod.StorageConsistencyApprovalRequiredError):
        await service.cleanup_orphans(
            safe_mode=False,
            minimum_orphan_age_seconds=24 * 3600,
            approval_token="wrong-token",
        )


@pytest.mark.asyncio
async def test_cleanup_orphans_retains_young_objects_until_minimum_age(monkeypatch, db_session, test_tenants):
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
                age_seconds=3600,
            )
        ],
        orphan_summary=storage_consistency_mod.StorageOrphanSummary(
            orphan_count=1,
            eligible_delete_count=0,
            retained_count=1,
            minimum_age_seconds=24 * 3600,
            approval_token="token-retain",
        ),
    )
    mock_delete = AsyncMock()

    monkeypatch.setattr(service, "scan_db_vs_s3", AsyncMock(return_value=scan_result))
    monkeypatch.setattr(storage_consistency_mod, "delete_storage_file", mock_delete)

    actions = await service.cleanup_orphans(
        safe_mode=False,
        minimum_orphan_age_seconds=24 * 3600,
        approval_token="token-retain",
    )

    assert actions == [
        storage_consistency_mod.StorageCleanupAction(
            org_id=test_tenants["org_a"],
            key=seeded["orphan_key"],
            action="delete_retained_minimum_age",
            project_id=seeded["project_id"],
            age_seconds=3600,
        )
    ]
    mock_delete.assert_not_awaited()
