from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

import structlog

from app.repositories.storage_consistency_repository import (
    ExportStorageReference,
    PhotoStorageReference,
    StorageConsistencyRepository,
)
from app.storage.backend import delete_storage_file, list_storage_keys

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StorageConsistencyIssue:
    org_id: str | None
    key: str
    action: str
    source: str
    record_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class StorageCleanupAction:
    org_id: str | None
    key: str
    action: str


@dataclass(frozen=True)
class StorageConsistencyScanResult:
    missing_storage_objects: list[StorageConsistencyIssue]
    orphan_storage_objects: list[StorageConsistencyIssue]


class StorageConsistencyService:
    def __init__(self, repository: StorageConsistencyRepository):
        self.repository = repository

    async def scan_db_vs_s3(self) -> StorageConsistencyScanResult:
        photo_refs = await self.repository.list_photo_storage_references()
        export_refs = await self.repository.list_export_storage_references()
        storage_keys = await self._list_managed_storage_keys()

        managed_refs = [
            *[self._photo_ref_to_issue(reference) for reference in photo_refs],
            *[self._export_ref_to_issue(reference) for reference in export_refs],
        ]
        managed_keys = {reference.key for reference in managed_refs}

        missing_storage_objects = sorted(
            [reference for reference in managed_refs if reference.key not in storage_keys],
            key=lambda issue: (issue.key, issue.source, issue.record_id or ""),
        )
        orphan_storage_objects = await self._build_orphan_storage_objects(
            storage_keys=storage_keys,
            managed_keys=managed_keys,
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
            )

        return StorageConsistencyScanResult(
            missing_storage_objects=missing_storage_objects,
            orphan_storage_objects=orphan_storage_objects,
        )

    async def cleanup_orphans(self, *, safe_mode: bool = True) -> list[StorageCleanupAction]:
        scan_result = await self.scan_db_vs_s3()
        cleanup_actions: list[StorageCleanupAction] = []

        for orphan in scan_result.orphan_storage_objects:
            action = "delete_skipped_safe_mode" if safe_mode else "delete_orphan_storage_object"
            if not safe_mode:
                await delete_storage_file(relative_storage_key=orphan.key)
            logger.info(
                "storage.consistency.cleanup",
                org_id=orphan.org_id,
                key=orphan.key,
                action=action,
            )
            cleanup_actions.append(
                StorageCleanupAction(
                    org_id=orphan.org_id,
                    key=orphan.key,
                    action=action,
                )
            )

        return cleanup_actions

    async def _list_managed_storage_keys(self) -> set[str]:
        project_keys = await list_storage_keys(prefix="projects")
        export_keys = await list_storage_keys(prefix="exports")
        return set(project_keys) | set(export_keys)

    async def _build_orphan_storage_objects(
        self,
        *,
        storage_keys: set[str],
        managed_keys: set[str],
    ) -> list[StorageConsistencyIssue]:
        orphan_keys = sorted(storage_keys - managed_keys)
        project_ids = {
            project_id
            for key in orphan_keys
            if (project_id := self._project_id_from_storage_key(key)) is not None
        }
        project_org_map = await self.repository.get_project_org_map(project_ids)

        return [
            StorageConsistencyIssue(
                org_id=project_org_map.get(self._project_id_from_storage_key(key) or ""),
                key=key,
                action="orphan_storage_object",
                source="storage.scan",
                project_id=self._project_id_from_storage_key(key),
            )
            for key in orphan_keys
        ]

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
