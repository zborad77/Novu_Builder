from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import PurePosixPath
from typing import Literal

import structlog

from app.repositories.storage_consistency_repository import (
    ExportStorageReference,
    PhotoStorageReference,
    StorageConsistencyRepository,
)
from app.storage.backend import delete_storage_file, list_storage_objects

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StorageConsistencyIssue:
    org_id: str | None
    key: str
    action: str
    source: str
    record_id: str | None = None
    project_id: str | None = None
    last_modified_at: str | None = None
    age_seconds: float | None = None


@dataclass(frozen=True)
class StorageCleanupAction:
    org_id: str | None
    key: str
    action: str
    project_id: str | None = None
    age_seconds: float | None = None


@dataclass(frozen=True)
class StorageOrphanSummary:
    orphan_count: int
    eligible_delete_count: int
    retained_count: int
    minimum_age_seconds: int
    approval_token: str | None


@dataclass(frozen=True)
class StorageConsistencyScanResult:
    missing_storage_objects: list[StorageConsistencyIssue]
    orphan_storage_objects: list[StorageConsistencyIssue]
    orphan_summary: StorageOrphanSummary


class StorageConsistencyApprovalRequiredError(ValueError):
    """Raised when destructive orphan cleanup is requested without a valid approval token."""


class StorageConsistencyService:
    def __init__(self, repository: StorageConsistencyRepository):
        self.repository = repository

    async def scan_db_vs_s3(
        self,
        *,
        minimum_orphan_age_seconds: int = 0,
        now: datetime | None = None,
    ) -> StorageConsistencyScanResult:
        photo_refs = await self.repository.list_photo_storage_references()
        export_refs = await self.repository.list_export_storage_references()
        storage_objects = await self._list_managed_storage_objects()

        managed_refs = [
            *[self._photo_ref_to_issue(reference) for reference in photo_refs],
            *[self._export_ref_to_issue(reference) for reference in export_refs],
        ]
        managed_keys = {reference.key for reference in managed_refs}
        storage_keys = {str(item["key"]) for item in storage_objects}

        missing_storage_objects = sorted(
            [reference for reference in managed_refs if reference.key not in storage_keys],
            key=lambda issue: (issue.key, issue.source, issue.record_id or ""),
        )
        orphan_storage_objects = await self._build_orphan_storage_objects(
            storage_objects=storage_objects,
            managed_keys=managed_keys,
            now=now,
        )
        orphan_summary = self._build_orphan_summary(
            orphan_storage_objects,
            minimum_orphan_age_seconds=minimum_orphan_age_seconds,
        )

        for issue in missing_storage_objects:
            logger.warning(
                "storage.consistency.issue",
                org_id=issue.org_id,
                key=issue.key,
                action=issue.action,
                source=issue.source,
                record_id=issue.record_id,
                project_id=issue.project_id,
            )

        for issue in orphan_storage_objects:
            logger.warning(
                "storage.consistency.issue",
                org_id=issue.org_id,
                key=issue.key,
                action=issue.action,
                source=issue.source,
                record_id=issue.record_id,
                project_id=issue.project_id,
                last_modified_at=issue.last_modified_at,
                age_seconds=issue.age_seconds,
            )

        return StorageConsistencyScanResult(
            missing_storage_objects=missing_storage_objects,
            orphan_storage_objects=orphan_storage_objects,
            orphan_summary=orphan_summary,
        )

    async def cleanup_orphans(
        self,
        *,
        safe_mode: bool = True,
        minimum_orphan_age_seconds: int = 0,
        approval_token: str | None = None,
        now: datetime | None = None,
    ) -> list[StorageCleanupAction]:
        scan_result = await self.scan_db_vs_s3(
            minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            now=now,
        )
        cleanup_actions: list[StorageCleanupAction] = []

        if not safe_mode:
            expected_token = scan_result.orphan_summary.approval_token
            if expected_token is None or approval_token != expected_token:
                raise StorageConsistencyApprovalRequiredError(
                    "Destructive orphan cleanup requires a matching approval token from a fresh dry-run report."
                )

        for orphan in scan_result.orphan_storage_objects:
            if safe_mode:
                action = "delete_skipped_safe_mode"
            elif not self._is_orphan_eligible_for_delete(
                orphan,
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            ):
                action = "delete_retained_minimum_age"
            else:
                action = "delete_orphan_storage_object"
                await delete_storage_file(relative_storage_key=orphan.key)

            logger.info(
                "storage.consistency.cleanup",
                org_id=orphan.org_id,
                key=orphan.key,
                action=action,
                project_id=orphan.project_id,
                age_seconds=orphan.age_seconds,
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            )
            cleanup_actions.append(
                StorageCleanupAction(
                    org_id=orphan.org_id,
                    key=orphan.key,
                    action=action,
                    project_id=orphan.project_id,
                    age_seconds=orphan.age_seconds,
                )
            )

        return cleanup_actions

    async def _list_managed_storage_objects(self) -> list[dict[str, object]]:
        project_objects = await list_storage_objects(prefix="projects")
        export_objects = await list_storage_objects(prefix="exports")
        return [*project_objects, *export_objects]

    async def _build_orphan_storage_objects(
        self,
        *,
        storage_objects: list[dict[str, object]],
        managed_keys: set[str],
        now: datetime | None = None,
    ) -> list[StorageConsistencyIssue]:
        orphan_objects = sorted(
            (item for item in storage_objects if str(item["key"]) not in managed_keys),
            key=lambda item: str(item["key"]),
        )
        project_ids = {
            project_id
            for item in orphan_objects
            if (project_id := self._project_id_from_storage_key(str(item["key"]))) is not None
        }
        project_org_map = await self.repository.get_project_org_map(project_ids)
        current_time = datetime.now(UTC) if now is None else now.astimezone(UTC)

        issues: list[StorageConsistencyIssue] = []
        for item in orphan_objects:
            key = str(item["key"])
            project_id = self._project_id_from_storage_key(key)
            last_modified = item.get("last_modified_at")
            age_seconds = self._compute_age_seconds(last_modified, current_time)
            issues.append(
                StorageConsistencyIssue(
                    org_id=project_org_map.get(project_id or ""),
                    key=key,
                    action="orphan_storage_object",
                    source="storage.scan",
                    project_id=project_id,
                    last_modified_at=self._serialize_datetime(last_modified),
                    age_seconds=age_seconds,
                )
            )
        return issues

    @staticmethod
    def _photo_ref_to_issue(reference: PhotoStorageReference) -> StorageConsistencyIssue:
        return StorageConsistencyIssue(
            org_id=reference.organization_id,
            key=reference.storage_key,
            action="missing_storage_object",
            source=f"db.project_photo.{reference.variant}",
            record_id=reference.photo_id,
            project_id=reference.project_id,
        )

    @staticmethod
    def _export_ref_to_issue(reference: ExportStorageReference) -> StorageConsistencyIssue:
        return StorageConsistencyIssue(
            org_id=reference.organization_id,
            key=reference.storage_key,
            action="missing_storage_object",
            source="db.project_export.storage",
            record_id=reference.export_id,
            project_id=reference.project_id,
        )

    @staticmethod
    def _project_id_from_storage_key(storage_key: str) -> str | None:
        parts = PurePosixPath(storage_key).parts
        if len(parts) < 2:
            return None
        if parts[0] == "projects":
            return parts[1]
        if parts[0] == "exports":
            return parts[1]
        return None

    @staticmethod
    def _serialize_datetime(value: object) -> str | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _compute_age_seconds(value: object, now: datetime) -> float | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return max(0.0, round((now - value.astimezone(UTC)).total_seconds(), 1))

    @classmethod
    def build_orphan_approval_token(
        cls,
        orphan_storage_objects: list[StorageConsistencyIssue],
        *,
        minimum_orphan_age_seconds: int,
    ) -> str | None:
        if not orphan_storage_objects:
            return None
        digest = hashlib.sha256()
        digest.update(f"min_age={int(max(0, minimum_orphan_age_seconds))}".encode("utf-8"))
        for orphan in sorted(orphan_storage_objects, key=lambda issue: issue.key):
            digest.update(orphan.key.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()[:16]

    @classmethod
    def _build_orphan_summary(
        cls,
        orphan_storage_objects: list[StorageConsistencyIssue],
        *,
        minimum_orphan_age_seconds: int,
    ) -> StorageOrphanSummary:
        eligible_delete_count = sum(
            1
            for orphan in orphan_storage_objects
            if cls._is_orphan_eligible_for_delete(
                orphan,
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            )
        )
        retained_count = len(orphan_storage_objects) - eligible_delete_count
        return StorageOrphanSummary(
            orphan_count=len(orphan_storage_objects),
            eligible_delete_count=eligible_delete_count,
            retained_count=retained_count,
            minimum_age_seconds=max(0, int(minimum_orphan_age_seconds)),
            approval_token=cls.build_orphan_approval_token(
                orphan_storage_objects,
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            ),
        )

    @staticmethod
    def _is_orphan_eligible_for_delete(
        orphan: StorageConsistencyIssue,
        *,
        minimum_orphan_age_seconds: int,
    ) -> bool:
        minimum_age = max(0, int(minimum_orphan_age_seconds))
        if minimum_age == 0:
            return True
        if orphan.age_seconds is None:
            return False
        return orphan.age_seconds >= minimum_age

    async def build_consistency_report(
        self,
        *,
        minimum_orphan_age_seconds: int = 0,
    ) -> "ConsistencyReport":
        """
        Run both direction scans and return a structured ConsistencyReport.

        DB→storage (blockers): any DB-referenced object missing from storage is a HARD FAIL.
        storage→DB (warnings): orphan storage objects are reported as warnings, not blockers.

        Fail-closed: if the underlying scan raises an exception, scan_status is set to
        "scan_partial" rather than silently reporting a clean state.
        """
        try:
            scan_result = await self.scan_db_vs_s3(
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            )
        except Exception as exc:
            logger.error("storage.consistency.scan_error", error=str(exc))
            return ConsistencyReport(
                scan_status="scan_partial",
                db_to_s3=DbToS3ScanResult(status="not_executed", blockers=[]),
                s3_to_db=S3ToDbScanResult(
                    status="not_executed",
                    warnings=[],
                    orphan_summary=StorageOrphanSummary(
                        orphan_count=0,
                        eligible_delete_count=0,
                        retained_count=0,
                        minimum_age_seconds=max(0, int(minimum_orphan_age_seconds)),
                        approval_token=None,
                    ),
                ),
                error_detail=str(exc),
            )

        db_to_s3 = DbToS3ScanResult(
            status="complete",
            blockers=scan_result.missing_storage_objects,
        )
        s3_to_db = S3ToDbScanResult(
            status="complete",
            warnings=scan_result.orphan_storage_objects,
            orphan_summary=scan_result.orphan_summary,
        )

        if db_to_s3.blockers:
            overall_status: Literal["scan_complete", "warning", "fail", "scan_partial"] = "fail"
        elif s3_to_db.warnings:
            overall_status = "warning"
        else:
            overall_status = "scan_complete"

        return ConsistencyReport(
            scan_status=overall_status,
            db_to_s3=db_to_s3,
            s3_to_db=s3_to_db,
        )


@dataclass(frozen=True)
class DbToS3ScanResult:
    status: Literal["complete", "not_executed"]
    blockers: list[StorageConsistencyIssue]


@dataclass(frozen=True)
class S3ToDbScanResult:
    status: Literal["complete", "partial", "not_executed"]
    warnings: list[StorageConsistencyIssue]
    orphan_summary: StorageOrphanSummary


@dataclass(frozen=True)
class ConsistencyReport:
    scan_status: Literal["scan_complete", "warning", "fail", "scan_partial"]
    db_to_s3: DbToS3ScanResult
    s3_to_db: S3ToDbScanResult
    error_detail: str | None = None
