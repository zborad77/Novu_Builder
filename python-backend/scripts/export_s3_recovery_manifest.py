#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.repositories.storage_consistency_repository import (  # noqa: E402
    ExportStorageReference,
    PhotoStorageReference,
    StorageConsistencyRepository,
)
from app.storage.s3_photo_storage import _build_s3_client_kwargs  # noqa: E402


@dataclass(frozen=True)
class StorageReference:
    source: str
    organization_id: str
    project_id: str
    record_id: str
    storage_key: str


@dataclass(frozen=True)
class ManifestObject:
    key: str
    version_id: str
    size: int
    etag: str | None
    last_modified_at: str | None
    references: list[dict[str, str]]


def _normalize_async_database_url(database_url: str) -> str:
    normalized = database_url.strip()
    if not normalized:
        raise ValueError("database URL is required")

    if normalized.startswith("postgresql+asyncpg://"):
        return normalized
    if normalized.startswith("postgresql+psycopg://"):
        return normalized.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
    if normalized.startswith("postgres://"):
        return normalized.replace("postgres://", "postgresql+asyncpg://", 1)
    if normalized.startswith("sqlite+aiosqlite:///"):
        return normalized
    if normalized.startswith("sqlite:///"):
        return normalized.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    raise ValueError(f"unsupported database URL scheme: {normalized!r}")


def _build_s3_client(*, region: str):
    import boto3  # type: ignore[import]

    kwargs = dict(_build_s3_client_kwargs())
    kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)


def _storage_reference_from_photo(reference: PhotoStorageReference) -> StorageReference:
    return StorageReference(
        source=f"db.project_photo.{reference.variant}",
        organization_id=reference.organization_id,
        project_id=reference.project_id,
        record_id=reference.photo_id,
        storage_key=reference.storage_key,
    )


def _storage_reference_from_export(reference: ExportStorageReference) -> StorageReference:
    return StorageReference(
        source="db.project_export.storage",
        organization_id=reference.organization_id,
        project_id=reference.project_id,
        record_id=reference.export_id,
        storage_key=reference.storage_key,
    )


async def _load_storage_references(database_url: str) -> list[StorageReference]:
    engine = create_async_engine(_normalize_async_database_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            repository = StorageConsistencyRepository(session)
            photo_refs = await repository.list_photo_storage_references()
            export_refs = await repository.list_export_storage_references()
            references = [_storage_reference_from_photo(item) for item in photo_refs]
            references.extend(_storage_reference_from_export(item) for item in export_refs)
            return sorted(references, key=lambda item: (item.storage_key, item.source, item.record_id))
    finally:
        await engine.dispose()


def _group_references_by_key(references: list[StorageReference]) -> dict[str, list[StorageReference]]:
    grouped: dict[str, list[StorageReference]] = {}
    for reference in references:
        grouped.setdefault(reference.storage_key, []).append(reference)
    return grouped


def _serialize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return str(value)


def _build_object_manifest(
    *,
    bucket: str,
    region: str,
    grouped_references: dict[str, list[StorageReference]],
) -> list[ManifestObject]:
    client = _build_s3_client(region=region)
    objects: list[ManifestObject] = []

    for storage_key in sorted(grouped_references):
        response = client.head_object(Bucket=bucket, Key=storage_key)
        version_id = response.get("VersionId")
        if not isinstance(version_id, str) or not version_id.strip():
            raise RuntimeError(
                f"S3 object {storage_key!r} in bucket {bucket!r} has no VersionId. "
                "Full-state DR requires a versioned recovery point for every referenced object."
            )

        size = int(response.get("ContentLength", 0))
        if size < 0:
            raise RuntimeError(f"S3 object {storage_key!r} reported a negative ContentLength.")

        objects.append(
            ManifestObject(
                key=storage_key,
                version_id=version_id,
                size=size,
                etag=response.get("ETag"),
                last_modified_at=_serialize_timestamp(response.get("LastModified")),
                references=[
                    {
                        "source": reference.source,
                        "organization_id": reference.organization_id,
                        "project_id": reference.project_id,
                        "record_id": reference.record_id,
                    }
                    for reference in grouped_references[storage_key]
                ],
            )
        )

    return objects


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a version-pinned S3 recovery manifest for DB-referenced media.")
    parser.add_argument("--database-url", required=True, help="Database URL for the authoritative DB snapshot.")
    parser.add_argument("--output", required=True, help="Output JSON path for the generated media manifest.")
    parser.add_argument("--bucket", required=True, help="Authoritative S3 bucket that stores production media.")
    parser.add_argument("--region", required=True, help="Authoritative S3 region.")
    parser.add_argument(
        "--declared-recovery-point",
        required=True,
        help="Human-readable recovery point label recorded in the DB backup manifest.",
    )
    parser.add_argument("--db-backup-file", required=True, help="Basename of the paired DB backup artifact.")
    parser.add_argument("--db-manifest-file", required=True, help="Basename of the paired DB manifest file.")
    return parser


async def _async_main() -> int:
    args = _build_parser().parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    references = await _load_storage_references(args.database_url)
    grouped_references = _group_references_by_key(references)
    objects = _build_object_manifest(
        bucket=args.bucket,
        region=args.region,
        grouped_references=grouped_references,
    )

    payload = {
        "format": "novu-s3-media-manifest-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "db_backup_file": args.db_backup_file,
        "db_manifest_file": args.db_manifest_file,
        "source_bucket": args.bucket,
        "source_region": args.region,
        "declared_recovery_point": args.declared_recovery_point,
        "storage_snapshot_consistent": True,
        "source_reference_count": len(references),
        "unique_object_count": len(objects),
        "objects": [asdict(item) for item in objects],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "unique_object_count": len(objects),
                "source_reference_count": len(references),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
