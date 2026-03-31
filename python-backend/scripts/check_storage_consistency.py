#!/usr/bin/env python
"""
Storage consistency checker for DB <-> storage references.

Modes:
  - full   : DB->storage and storage->DB scan
  - sample : DB->storage sample only

Cleanup:
  - default is dry-run/report only
  - destructive orphan cleanup requires:
      * --cleanup
      * full scan mode
      * a matching --approval-token from the dry-run output
      * orphan age >= --min-orphan-age-hours
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.repositories.storage_consistency_repository import StorageConsistencyRepository  # noqa: E402
from app.services.storage_consistency_service import (  # noqa: E402
    ConsistencyReport,
    DbToS3ScanResult,
    S3ToDbScanResult,
    StorageCleanupAction,
    StorageConsistencyApprovalRequiredError,
    StorageConsistencyIssue,
    StorageConsistencyService,
)
from app.storage.backend import storage_key_exists  # noqa: E402


def _sanitize(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def emit_scan_status(status: str, detail: str) -> None:
    print(f"STORAGE_CONSISTENCY_SCAN_STATUS|{_sanitize(status)}|{_sanitize(detail)}")


def emit_blocker(issue: StorageConsistencyIssue) -> None:
    print(
        f"STORAGE_CONSISTENCY_BLOCKER"
        f"|{_sanitize(issue.key)}"
        f"|{_sanitize(issue.source)}"
        f"|{_sanitize(issue.record_id or '')}"
        f"|{_sanitize(issue.org_id or '')}"
        f"|{_sanitize(issue.project_id or '')}"
    )


def emit_warning(issue: StorageConsistencyIssue) -> None:
    print(
        f"STORAGE_CONSISTENCY_WARNING"
        f"|{_sanitize(issue.key)}"
        f"|{_sanitize(issue.source)}"
        f"|{_sanitize(issue.org_id or '')}"
        f"|{_sanitize(issue.project_id or '')}"
    )


def emit_orphan_summary(report: ConsistencyReport) -> None:
    summary = report.s3_to_db.orphan_summary
    print(
        f"STORAGE_CONSISTENCY_ORPHAN_SUMMARY"
        f"|count={summary.orphan_count}"
        f"|eligible={summary.eligible_delete_count}"
        f"|retained={summary.retained_count}"
        f"|min_age_seconds={summary.minimum_age_seconds}"
        f"|approval_token={_sanitize(summary.approval_token or '')}"
    )


def emit_cleanup_action(action: StorageCleanupAction) -> None:
    print(
        f"STORAGE_CONSISTENCY_CLEANUP_ACTION"
        f"|{_sanitize(action.key)}"
        f"|{_sanitize(action.action)}"
        f"|{_sanitize(action.org_id or '')}"
        f"|{_sanitize(action.project_id or '')}"
    )


def emit_report_json(report: ConsistencyReport) -> None:
    payload = {
        "scan_status": report.scan_status,
        "db_to_s3": {
            "status": report.db_to_s3.status,
            "blocker_count": len(report.db_to_s3.blockers),
            "blockers": [asdict(item) for item in report.db_to_s3.blockers],
        },
        "s3_to_db": {
            "status": report.s3_to_db.status,
            "warning_count": len(report.s3_to_db.warnings),
            "warnings": [asdict(item) for item in report.s3_to_db.warnings],
            "orphan_summary": asdict(report.s3_to_db.orphan_summary),
        },
        "error_detail": report.error_detail,
    }
    print("STORAGE_CONSISTENCY_REPORT_JSON=" + json.dumps(payload, separators=(",", ":"), sort_keys=True))


def print_human_report(report: ConsistencyReport, *, mode: str, sample_size: int | None) -> None:
    summary = report.s3_to_db.orphan_summary
    sep = "=" * 60
    print(sep)
    print("Storage Consistency Report")
    print(sep)
    print(f"  Scan mode:    {mode}" + (f" (sample_size={sample_size})" if mode == "sample" else ""))
    print(f"  Scan status:  {report.scan_status.upper()}")
    if report.error_detail:
        print(f"  Error detail: {report.error_detail}")
    print()

    print(f"  DB->storage direction [{report.db_to_s3.status}]")
    if report.db_to_s3.blockers:
        print(f"    BLOCKERS ({len(report.db_to_s3.blockers)} - HARD FAIL):")
        for blocker in report.db_to_s3.blockers:
            print(
                f"      key={blocker.key}"
                f" source={blocker.source}"
                f" record_id={blocker.record_id}"
                f" org={blocker.org_id}"
            )
    else:
        print("    No blockers - all checked DB references exist in storage.")

    print()
    print(f"  storage->DB direction [{report.s3_to_db.status}]")
    if report.s3_to_db.warnings:
        print(f"    WARNINGS ({len(report.s3_to_db.warnings)} orphan objects):")
        for warning in report.s3_to_db.warnings:
            age = f" age={warning.age_seconds}s" if warning.age_seconds is not None else ""
            print(f"      key={warning.key} org={warning.org_id} project={warning.project_id}{age}")
        print("    Orphans are warnings only - they do NOT block release without explicit policy.")
        print(
            "    Cleanup gate:"
            f" eligible={summary.eligible_delete_count}"
            f" retained={summary.retained_count}"
            f" min_age_seconds={summary.minimum_age_seconds}"
        )
        if summary.approval_token:
            print(f"    Approval token for delete mode: {summary.approval_token}")
    elif report.s3_to_db.status == "not_executed":
        print("    NOT EXECUTED - orphan scan was not run in this mode.")
    else:
        print("    No orphan storage objects found.")

    print()
    print(sep)


async def _run_sample_db_to_s3(
    session: AsyncSession,
    sample_size: int,
) -> DbToS3ScanResult:
    repository = StorageConsistencyRepository(session)
    photo_refs = await repository.list_photo_storage_references()
    export_refs = await repository.list_export_storage_references()

    candidates: list[tuple[str, str, str | None, str | None]] = []
    for ref in photo_refs:
        candidates.append((ref.storage_key, f"db.project_photo.{ref.variant}", ref.photo_id, ref.project_id))
    for ref in export_refs:
        candidates.append((ref.storage_key, "db.project_export.storage", ref.export_id, ref.project_id))

    sampled = candidates[:sample_size]
    blockers: list[StorageConsistencyIssue] = []

    for storage_key, source, record_id, project_id in sampled:
        exists = await storage_key_exists(relative_storage_key=storage_key)
        if not exists:
            blockers.append(
                StorageConsistencyIssue(
                    org_id=None,
                    key=storage_key,
                    action="missing_storage_object",
                    source=source,
                    record_id=record_id,
                    project_id=project_id,
                )
            )

    return DbToS3ScanResult(status="complete", blockers=blockers)


def _normalize_db_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("database URL is required")
    for prefix, replacement in (
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ):
        if normalized.startswith(prefix):
            return normalized.replace(prefix, replacement, 1)
    if normalized.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite:///")):
        return normalized
    raise ValueError(f"unsupported database URL scheme: {normalized!r}")


async def _run_with_service(database_url: str, coro_factory):
    engine = create_async_engine(_normalize_db_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            repository = StorageConsistencyRepository(session)
            service = StorageConsistencyService(repository)
            return await coro_factory(service)
    finally:
        await engine.dispose()


async def _run_full_scan(database_url: str, *, minimum_orphan_age_seconds: int) -> ConsistencyReport:
    return await _run_with_service(
        database_url,
        lambda service: service.build_consistency_report(
            minimum_orphan_age_seconds=minimum_orphan_age_seconds,
        ),
    )


async def _run_cleanup(
    database_url: str,
    *,
    minimum_orphan_age_seconds: int,
    approval_token: str,
) -> list[StorageCleanupAction]:
    return await _run_with_service(
        database_url,
        lambda service: service.cleanup_orphans(
            safe_mode=False,
            minimum_orphan_age_seconds=minimum_orphan_age_seconds,
            approval_token=approval_token,
        ),
    )


async def _run_sample_scan(database_url: str, sample_size: int) -> ConsistencyReport:
    engine = create_async_engine(_normalize_db_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            try:
                db_to_s3 = await _run_sample_db_to_s3(session, sample_size)
            except Exception as exc:
                return ConsistencyReport(
                    scan_status="scan_partial",
                    db_to_s3=DbToS3ScanResult(status="not_executed", blockers=[]),
                    s3_to_db=S3ToDbScanResult(
                        status="not_executed",
                        warnings=[],
                        orphan_summary=StorageConsistencyService._build_orphan_summary(
                            [],
                            minimum_orphan_age_seconds=0,
                        ),
                    ),
                    error_detail=str(exc),
                )

        s3_to_db = S3ToDbScanResult(
            status="not_executed",
            warnings=[],
            orphan_summary=StorageConsistencyService._build_orphan_summary(
                [],
                minimum_orphan_age_seconds=0,
            ),
        )
        return ConsistencyReport(
            scan_status="fail" if db_to_s3.blockers else "scan_partial",
            db_to_s3=db_to_s3,
            s3_to_db=s3_to_db,
        )
    finally:
        await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC"),
        help="Database URL (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "sample"],
        default="full",
        help="full scan (default) or DB->storage sample scan",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=int(os.getenv("STORAGE_CONSISTENCY_SAMPLE_SIZE", "10")),
        help="Sample size for sample mode",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Emit only machine-readable protocol lines",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete eligible orphan objects after a full scan",
    )
    parser.add_argument(
        "--approval-token",
        default="",
        help="Approval token from a previous dry-run orphan summary",
    )
    parser.add_argument(
        "--min-orphan-age-hours",
        type=int,
        default=int(os.getenv("STORAGE_ORPHAN_MIN_AGE_HOURS", "24")),
        help="Minimum orphan age before delete is eligible (default: 24h)",
    )
    return parser


async def _async_main() -> int:
    args = _build_parser().parse_args()

    if not args.database_url:
        print("ERROR: --database-url is required (or set DATABASE_URL)", file=sys.stderr)
        return 2
    if args.sample_size <= 0:
        print("ERROR: --sample-size must be > 0", file=sys.stderr)
        return 2
    if args.min_orphan_age_hours < 0:
        print("ERROR: --min-orphan-age-hours must be >= 0", file=sys.stderr)
        return 2
    if args.cleanup and args.mode != "full":
        print("ERROR: --cleanup is only supported in --mode full", file=sys.stderr)
        return 2

    minimum_orphan_age_seconds = args.min_orphan_age_hours * 3600
    if args.mode == "full":
        report = await _run_full_scan(
            args.database_url,
            minimum_orphan_age_seconds=minimum_orphan_age_seconds,
        )
    else:
        report = await _run_sample_scan(args.database_url, args.sample_size)

    blocker_count = len(report.db_to_s3.blockers)
    warning_count = len(report.s3_to_db.warnings)
    orphan_summary = report.s3_to_db.orphan_summary

    detail_parts = [f"db_to_s3={report.db_to_s3.status}"]
    if blocker_count:
        detail_parts.append(f"blockers={blocker_count}")
    detail_parts.append(f"s3_to_db={report.s3_to_db.status}")
    if warning_count:
        detail_parts.append(f"warnings={warning_count}")
    if orphan_summary.orphan_count:
        detail_parts.append(f"orphan_eligible={orphan_summary.eligible_delete_count}")
        detail_parts.append(f"orphan_retained={orphan_summary.retained_count}")
    if report.error_detail:
        detail_parts.append(f"error={report.error_detail}")

    emit_scan_status(report.scan_status, " ".join(detail_parts))
    for blocker in report.db_to_s3.blockers:
        emit_blocker(blocker)
    for warning in report.s3_to_db.warnings:
        emit_warning(warning)
    emit_orphan_summary(report)
    emit_report_json(report)

    cleanup_actions: list[StorageCleanupAction] = []
    if args.cleanup and report.scan_status in {"scan_complete", "warning"}:
        try:
            cleanup_actions = await _run_cleanup(
                args.database_url,
                minimum_orphan_age_seconds=minimum_orphan_age_seconds,
                approval_token=args.approval_token.strip(),
            )
        except StorageConsistencyApprovalRequiredError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        for action in cleanup_actions:
            emit_cleanup_action(action)

    if not args.json_only:
        print_human_report(report, mode=args.mode, sample_size=args.sample_size if args.mode == "sample" else None)
        if cleanup_actions:
            print(f"Cleanup actions executed: {len(cleanup_actions)}")

    if report.scan_status == "fail":
        return 1
    if report.scan_status == "scan_partial":
        return 2
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
