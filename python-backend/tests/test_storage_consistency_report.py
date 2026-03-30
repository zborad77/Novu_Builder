"""
Tests for StorageConsistencyService.build_consistency_report() semantics.

Focus: blocker vs warning distinction, scan_status values, fail-closed behaviour.
These tests mock scan_db_vs_s3() — they are not integration tests.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.storage_consistency_repository import StorageConsistencyRepository
from app.services import storage_consistency_service as mod
from app.services.storage_consistency_service import (
    ConsistencyReport,
    DbToS3ScanResult,
    S3ToDbScanResult,
    StorageConsistencyIssue,
    StorageConsistencyService,
    StorageConsistencyScanResult,
)


def _make_service() -> StorageConsistencyService:
    return StorageConsistencyService(repository=AsyncMock(spec=StorageConsistencyRepository))


def _missing_issue(key: str = "projects/p1/photo.jpg") -> StorageConsistencyIssue:
    return StorageConsistencyIssue(
        org_id="org_a",
        key=key,
        action="missing_storage_object",
        source="db.project_photo.original",
        record_id="photo_1",
        project_id="p1",
    )


def _orphan_issue(key: str = "projects/p1/orphan.jpg") -> StorageConsistencyIssue:
    return StorageConsistencyIssue(
        org_id="org_a",
        key=key,
        action="orphan_storage_object",
        source="storage.scan",
        record_id=None,
        project_id="p1",
    )


# ── scan_status semantics ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_report_all_clean_is_scan_complete():
    """No missing refs, no orphans → scan_complete; both directions complete."""
    service = _make_service()
    clean_result = StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=clean_result)):
        report = await service.build_consistency_report()

    assert report.scan_status == "scan_complete"
    assert report.db_to_s3.status == "complete"
    assert report.db_to_s3.blockers == []
    assert report.s3_to_db.status == "complete"
    assert report.s3_to_db.warnings == []
    assert report.error_detail is None


@pytest.mark.asyncio
async def test_build_report_missing_referenced_object_is_fail():
    """A DB-referenced key that is absent from storage → scan_status='fail'."""
    service = _make_service()
    issue = _missing_issue()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[issue],
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert report.scan_status == "fail"
    assert report.db_to_s3.blockers == [issue]
    assert report.s3_to_db.warnings == []


@pytest.mark.asyncio
async def test_build_report_missing_referenced_object_is_hard_fail_not_warning():
    """Missing referenced object must appear in blockers, NOT in warnings."""
    service = _make_service()
    issue = _missing_issue()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[issue],
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert issue in report.db_to_s3.blockers
    assert issue not in report.s3_to_db.warnings


@pytest.mark.asyncio
async def test_build_report_orphan_only_is_warning_not_fail():
    """Orphan storage object → scan_status='warning'; no blockers; not a hard fail."""
    service = _make_service()
    issue = _orphan_issue()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[issue],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert report.scan_status == "warning"
    assert report.db_to_s3.blockers == []
    assert report.s3_to_db.warnings == [issue]


@pytest.mark.asyncio
async def test_build_report_orphan_is_warning_not_placed_in_blockers():
    """Orphan must appear in warnings, NOT in blockers."""
    service = _make_service()
    issue = _orphan_issue()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[issue],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert issue in report.s3_to_db.warnings
    assert issue not in report.db_to_s3.blockers


@pytest.mark.asyncio
async def test_build_report_blocker_takes_precedence_over_warning():
    """When both a missing ref and an orphan exist, scan_status must be 'fail'."""
    service = _make_service()
    missing = _missing_issue()
    orphan = _orphan_issue()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[missing],
        orphan_storage_objects=[orphan],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert report.scan_status == "fail"
    assert report.db_to_s3.blockers == [missing]
    assert report.s3_to_db.warnings == [orphan]


@pytest.mark.asyncio
async def test_build_report_multiple_blockers_all_listed():
    """All missing referenced objects must be present in the blockers list."""
    service = _make_service()
    issues = [_missing_issue(f"projects/p1/photo_{i}.jpg") for i in range(5)]
    result = StorageConsistencyScanResult(
        missing_storage_objects=issues,
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert report.scan_status == "fail"
    assert len(report.db_to_s3.blockers) == 5
    assert set(b.key for b in report.db_to_s3.blockers) == {
        f"projects/p1/photo_{i}.jpg" for i in range(5)
    }


# ── fail-closed behaviour ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_report_scan_exception_is_scan_partial_not_clean():
    """
    If scan_db_vs_s3 raises an exception the report must be scan_partial,
    not scan_complete. The system must not silently claim a clean state.
    """
    service = _make_service()
    with patch.object(service, "scan_db_vs_s3", AsyncMock(side_effect=RuntimeError("S3 timeout"))):
        report = await service.build_consistency_report()

    assert report.scan_status == "scan_partial"
    assert report.db_to_s3.status == "not_executed"
    assert report.db_to_s3.blockers == []
    assert report.s3_to_db.status == "not_executed"
    assert report.s3_to_db.warnings == []
    assert report.error_detail is not None
    assert "S3 timeout" in report.error_detail


@pytest.mark.asyncio
async def test_build_report_scan_partial_does_not_claim_success():
    """scan_partial must not be treated as success by callers."""
    service = _make_service()
    with patch.object(service, "scan_db_vs_s3", AsyncMock(side_effect=Exception("connection refused"))):
        report = await service.build_consistency_report()

    assert report.scan_status not in ("scan_complete", "warning")


# ── direction status fields ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_report_both_directions_complete_on_clean_scan():
    """Both db_to_s3.status and s3_to_db.status must be 'complete' on a clean full scan."""
    service = _make_service()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert report.db_to_s3.status == "complete"
    assert report.s3_to_db.status == "complete"


@pytest.mark.asyncio
async def test_build_report_scan_error_marks_both_directions_not_executed():
    """On exception, both direction statuses must be 'not_executed'."""
    service = _make_service()
    with patch.object(service, "scan_db_vs_s3", AsyncMock(side_effect=IOError("network error"))):
        report = await service.build_consistency_report()

    assert report.db_to_s3.status == "not_executed"
    assert report.s3_to_db.status == "not_executed"


# ── type assertions ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_report_returns_consistency_report_dataclass():
    """Return type must be ConsistencyReport with the expected sub-dataclasses."""
    service = _make_service()
    result = StorageConsistencyScanResult(
        missing_storage_objects=[],
        orphan_storage_objects=[],
    )
    with patch.object(service, "scan_db_vs_s3", AsyncMock(return_value=result)):
        report = await service.build_consistency_report()

    assert isinstance(report, ConsistencyReport)
    assert isinstance(report.db_to_s3, DbToS3ScanResult)
    assert isinstance(report.s3_to_db, S3ToDbScanResult)
