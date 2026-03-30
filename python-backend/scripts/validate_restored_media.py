#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import ProjectExport, ProjectPhoto  # noqa: E402
from app.repositories.storage_consistency_repository import (  # noqa: E402
    ExportStorageReference,
    PhotoStorageReference,
    StorageConsistencyRepository,
)
from app.services.photo_service import to_read_model  # noqa: E402
from app.storage.backend import generate_presigned_url, storage_key_exists  # noqa: E402

ValidationStatus = Literal["PASSED", "FAILED", "NOT EXECUTED", "OUT OF SCOPE"]


@dataclass(frozen=True)
class SampleReference:
    source: str
    record_id: str
    project_id: str
    storage_key: str


@dataclass(frozen=True)
class StepResult:
    status: ValidationStatus
    detail: str


@dataclass(frozen=True)
class ValidationSummary:
    selected_references: list[SampleReference]
    reference_sample_validation: StepResult
    signed_url_validation: StepResult
    app_media_smoke: StepResult


def _sanitize_detail(detail: str) -> str:
    return " ".join(detail.replace("|", "/").split())


def _emit_step(name: str, result: StepResult) -> None:
    print(f"POST_RESTORE_VALIDATION_STEP|{name}|{result.status}|{_sanitize_detail(result.detail)}")


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


def _to_sample_reference_from_photo(reference: PhotoStorageReference) -> SampleReference:
    return SampleReference(
        source=f"db.project_photo.{reference.variant}",
        record_id=reference.photo_id,
        project_id=reference.project_id,
        storage_key=reference.storage_key,
    )


def _to_sample_reference_from_export(reference: ExportStorageReference) -> SampleReference:
    return SampleReference(
        source="db.project_export.storage",
        record_id=reference.export_id,
        project_id=reference.project_id,
        storage_key=reference.storage_key,
    )


def _select_reference_sample(
    *,
    photo_references: list[PhotoStorageReference],
    export_references: list[ExportStorageReference],
    sample_size: int,
) -> list[SampleReference]:
    selected: list[SampleReference] = []
    seen: set[tuple[str, str, str]] = set()

    def add(reference: SampleReference | None) -> None:
        if reference is None or len(selected) >= sample_size:
            return
        identity = (reference.source, reference.record_id, reference.storage_key)
        if identity in seen:
            return
        seen.add(identity)
        selected.append(reference)

    first_original = next((ref for ref in photo_references if ref.variant == "original"), None)
    first_derived = next((ref for ref in photo_references if ref.variant in {"preview", "ai_input"}), None)
    first_export = export_references[0] if export_references else None

    add(_to_sample_reference_from_photo(first_original) if first_original else None)
    add(_to_sample_reference_from_photo(first_derived) if first_derived else None)
    add(_to_sample_reference_from_export(first_export) if first_export else None)

    for reference in photo_references:
        add(_to_sample_reference_from_photo(reference))
    for reference in export_references:
        add(_to_sample_reference_from_export(reference))

    return selected


async def _reference_sample_validation(selected_references: list[SampleReference]) -> StepResult:
    if not selected_references:
        return StepResult(
            status="OUT OF SCOPE",
            detail="database contains no photo or export storage references",
        )

    for reference in selected_references:
        try:
            exists = await storage_key_exists(relative_storage_key=reference.storage_key)
        except Exception as exc:
            return StepResult(
                status="FAILED",
                detail=(
                    "storage existence check raised an error for "
                    f"source={reference.source} record_id={reference.record_id} key={reference.storage_key}: {exc}"
                ),
            )
        if not exists:
            return StepResult(
                status="FAILED",
                detail=(
                    "missing DB-referenced object "
                    f"source={reference.source} record_id={reference.record_id} key={reference.storage_key}"
                ),
            )

    return StepResult(
        status="PASSED",
        detail=f"validated {len(selected_references)} sampled DB-to-storage references",
    )


def _signed_url_validation(selected_references: list[SampleReference]) -> StepResult:
    if not selected_references:
        return StepResult(
            status="OUT OF SCOPE",
            detail="no sampled storage references are available for signed URL validation",
        )

    sample = selected_references[0]
    try:
        url = generate_presigned_url(sample.storage_key)
    except Exception as exc:
        return StepResult(
            status="FAILED",
            detail=f"signed URL generation raised an error for key={sample.storage_key}: {exc}",
        )
    if not url:
        return StepResult(
            status="FAILED",
            detail=f"signed URL generation returned an empty value for key={sample.storage_key}",
        )

    backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        expected = f"/mock-storage/{sample.storage_key}"
        if url != expected:
            return StepResult(
                status="FAILED",
                detail=f"local access path mismatch for key={sample.storage_key}; expected={expected} actual={url}",
            )
    elif backend == "s3":
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return StepResult(
                status="FAILED",
                detail=f"signed URL is not a valid http(s) URL for key={sample.storage_key}",
            )
    else:
        return StepResult(
            status="OUT OF SCOPE",
            detail=f"storage backend {backend!r} is not supported by this validation helper",
        )

    return StepResult(
        status="PASSED",
        detail=f"signed URL or access path generated for sampled key={sample.storage_key}",
    )


async def _app_media_smoke(session: AsyncSession, selected_references: list[SampleReference]) -> StepResult:
    photo_ids = [reference.record_id for reference in selected_references if reference.source.startswith("db.project_photo.")]
    if not photo_ids:
        return StepResult(
            status="OUT OF SCOPE",
            detail="no sampled project photo references are available for read-model smoke validation",
        )

    result = await session.execute(
        select(ProjectPhoto)
        .where(ProjectPhoto.id.in_(photo_ids))
        .order_by(ProjectPhoto.id.asc())
    )
    photos = {photo.id: photo for photo in result.scalars().all()}

    sampled_photo = next((photos.get(photo_id) for photo_id in photo_ids if photo_id in photos), None)
    if sampled_photo is None:
        return StepResult(
            status="FAILED",
            detail="sampled project photo record could not be reloaded for read-model smoke validation",
        )

    try:
        read_model = to_read_model(sampled_photo)
    except Exception as exc:
        return StepResult(
            status="FAILED",
            detail=f"photo read-model smoke raised an error for photo_id={sampled_photo.id}: {exc}",
        )
    if read_model.storageKey != sampled_photo.storage_key or not read_model.url:
        return StepResult(
            status="FAILED",
            detail=f"photo read model did not expose original media URL for photo_id={sampled_photo.id}",
        )

    if sampled_photo.preview_storage_key:
        preview_variant = read_model.variants.preview
        if preview_variant.storageKey != sampled_photo.preview_storage_key or not preview_variant.url:
            return StepResult(
                status="FAILED",
                detail=f"photo read model did not expose preview media URL for photo_id={sampled_photo.id}",
            )

    return StepResult(
        status="PASSED",
        detail=f"photo read-model smoke validated for photo_id={sampled_photo.id}",
    )


async def _run_validation(*, database_url: str, sample_size: int) -> ValidationSummary:
    engine = create_async_engine(_normalize_async_database_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_factory() as session:
            repository = StorageConsistencyRepository(session)
            photo_references = await repository.list_photo_storage_references()
            export_references = await repository.list_export_storage_references()
            selected_references = _select_reference_sample(
                photo_references=photo_references,
                export_references=export_references,
                sample_size=sample_size,
            )
            reference_sample_validation = await _reference_sample_validation(selected_references)
            signed_url_validation = (
                _signed_url_validation(selected_references)
                if reference_sample_validation.status != "FAILED"
                else StepResult(status="NOT EXECUTED", detail="skipped because sampled DB-to-storage validation failed")
            )
            app_media_smoke = (
                await _app_media_smoke(session, selected_references)
                if reference_sample_validation.status != "FAILED"
                else StepResult(status="NOT EXECUTED", detail="skipped because sampled DB-to-storage validation failed")
            )

            return ValidationSummary(
                selected_references=selected_references,
                reference_sample_validation=reference_sample_validation,
                signed_url_validation=signed_url_validation,
                app_media_smoke=app_media_smoke,
            )
    finally:
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate sampled DB-to-storage references after restore.")
    parser.add_argument(
        "--database-url",
        required=True,
        help="database URL for the restored database (sync or async PostgreSQL/SQLite URL)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=int(os.getenv("RESTORE_STORAGE_REFERENCE_SAMPLE_SIZE", "3")),
        help="maximum number of DB-to-storage references to validate",
    )
    return parser


async def _async_main() -> int:
    args = _build_parser().parse_args()
    if args.sample_size <= 0:
        raise SystemExit("sample size must be > 0")

    summary = await _run_validation(
        database_url=args.database_url,
        sample_size=args.sample_size,
    )

    _emit_step("reference_sample_validation", summary.reference_sample_validation)
    _emit_step("signed_url_validation", summary.signed_url_validation)
    _emit_step("app_media_smoke", summary.app_media_smoke)
    print(
        "POST_RESTORE_VALIDATION_JSON="
        + json.dumps(
            {
                "selected_references": [asdict(reference) for reference in summary.selected_references],
                "reference_sample_validation": asdict(summary.reference_sample_validation),
                "signed_url_validation": asdict(summary.signed_url_validation),
                "app_media_smoke": asdict(summary.app_media_smoke),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )

    if any(
        step.status == "FAILED"
        for step in (
            summary.reference_sample_validation,
            summary.signed_url_validation,
            summary.app_media_smoke,
        )
    ):
        return 1
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
