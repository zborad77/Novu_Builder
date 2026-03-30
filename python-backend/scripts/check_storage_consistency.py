#!/usr/bin/env python
"""
Storage consistency checker — DB<->S3 reference validation.

Two-direction scan
──────────────────
  DB→S3  (blockers)  Verifies every DB-referenced storage object exists in the backend.
                     Missing referenced object = HARD FAIL (exit 1).
  S3→DB  (warnings)  Identifies storage objects that have no DB reference (orphans).
                     Orphan object = WARNING, reported but does not block by itself (exit 0).

Scan modes
──────────
  full    (default)  Both directions.  Requires storage listing capability.
  sample             DB→S3 only, up to --sample-size references checked individually.
                     S3→DB direction is marked NOT_EXECUTED — cannot orphan-check a subset.
                     Output scan_status = "scan_partial" unless a blocker is found.

Exit codes
──────────
  0   scan_complete  Both directions clean.
  0   warning        Orphans found, no blockers.  Caller should inspect the report.
  1   fail           One or more DB-referenced objects are missing (HARD FAIL).
  2   scan_partial   Scan could not complete (fail-closed: clean state cannot be confirmed).

Output format
─────────────
  STORAGE_CONSISTENCY_SCAN_STATUS|<status>|<detail>
  STORAGE_CONSISTENCY_BLOCKER|<key>|<source>|<record_id>|<org_id>|<project_id>
  STORAGE_CONSISTENCY_WARNING|<key>|<source>|<org_id>|<project_id>
  STORAGE_CONSISTENCY_REPORT_JSON=<json>
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
    StorageConsistencyIssue,
    StorageConsistencyService,
)
from app.storage.backend import storage_key_exists  # noqa: E402

# ── output protocol ──────────────────────────────────────────────────────────


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


def emit_report_json(report: ConsistencyReport) -> None:
    payload = {
        "scan_status": report.scan_status,
        "db_to_s3": {
            "status": report.db_to_s3.status,
            "blocker_count": len(report.db_to_s3.blockers),
            "blockers": [asdict(b) for b in report.db_to_s3.blockers],
        },
        "s3_to_db": {
            "status": report.s3_to_db.status,
            "warning_count": len(report.s3_to_db.warnings),
            "warnings": [asdict(w) for w in report.s3_to_db.warnings],
        },
        "error_detail": report.error_detail,
    }
    print("STORAGE_CONSISTENCY_REPORT_JSON=" + json.dumps(payload, separators=(",", ":"), sort_keys=True))


# ── human-readable report ─────────────────────────────────────────────────────


def print_human_report(report: ConsistencyReport, *, mode: str, sample_size: int | None) -> None:
    sep = "=" * 60
    print(sep)
    print("Storage Consistency Report")
    print(sep)
    print(f"  Scan mode:    {mode}" + (f" (sample_size={sample_size})" if mode == "sample" else ""))
    print(f"  Scan status:  {report.scan_status.upper()}")
    if report.error_detail:
        print(f"  Error detail: {report.error_detail}")
    print()

    print(f"  DB→S3 direction [{report.db_to_s3.status}]")
    if report.db_to_s3.blockers:
        print(f"    BLOCKERS ({len(report.db_to_s3.blockers)} — HARD FAIL):")
        for b in report.db_to_s3.blockers:
            print(f"      key={b.key} source={b.source} record_id={b.record_id} org={b.org_id}")
    else:
        print("    No blockers — all checked DB references exist in storage.")

    print()
    print(f"  S3→DB direction [{report.s3_to_db.status}]")
    if report.s3_to_db.warnings:
        print(f"    WARNINGS ({len(report.s3_to_db.warnings)} orphan objects):")
        for w in report.s3_to_db.warnings:
            print(f"      key={w.key} org={w.org_id} project={w.project_id}")
        print("    Orphans are reported only — they do NOT block release without explicit policy.")
        print("    Future cleanup: run StorageConsistencyService.cleanup_orphans(safe_mode=True)")
    elif report.s3_to_db.status == "not_executed":
        print("    NOT EXECUTED — S3→DB orphan scan was not run in this mode.")
    else:
        print("    No orphan storage objects found.")

    print()
    print(sep)


# ── sample DB→S3 scan ─────────────────────────────────────────────────────────


async def _run_sample_db_to_s3(
    session: AsyncSession,
    sample_size: int,
) -> DbToS3ScanResult:
    """
    Sample mode: individually checks existence of up to sample_size DB-referenced keys.
    Deterministic — always samples the first N references ordered by (org, project, id).
    S3→DB direction is not run; orphan detection cannot be sampled meaningfully.
    """
    repository = StorageConsistencyRepository(session)
    photo_refs = await repository.list_photo_storage_references()
    export_refs = await repository.list_export_storage_references()

    candidates: list[tuple[str, str, str | None, str | None]] = []
    for ref in photo_refs:
        candidates.append((
            ref.storage_key,
            f"db.project_photo.{ref.variant}",
            ref.photo_id,
            ref.project_id,
        ))
    for ref in export_refs:
        candidates.append((
            ref.storage_key,
            "db.project_export.storage",
            ref.export_id,
            ref.project_id,
        ))

    sampled = candidates[:sample_size]
    blockers: list[StorageConsistencyIssue] = []

    for storage_key, source, record_id, project_id in sampled:
        try:
            exists = await storage_key_exists(relative_storage_key=storage_key)
        except Exception as exc:
            return DbToS3ScanResult(
                status="not_executed",
                blockers=[
                    StorageConsistencyIssue(
                        org_id=None,
                        key=storage_key,
                        action="missing_storage_object",
                        source=source,
                        record_id=record_id,
                        project_id=project_id,
                    )
                ],
            )
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


# ── scan runners ──────────────────────────────────────────────────────────────


async def _run_full_scan(database_url: str) -> ConsistencyReport:
    engine = create_async_engine(_normalize_db_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            repository = StorageConsistencyRepository(session)
            service = StorageConsistencyService(repository)
            return await service.build_consistency_report()
    finally:
        await engine.dispose()


async def _run_sample_scan(database_url: str, sample_size: int) -> ConsistencyReport:
    engine = create_async_engine(_normalize_db_url(database_url), future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as session:
            try:
                db_to_s3 = await _run_sample_db_to_s3(session, sample_size)
            except Exception as exc:
                db_to_s3 = DbToS3ScanResult(status="not_executed", blockers=[])
                return ConsistencyReport(
                    scan_status="scan_partial",
                    db_to_s3=db_to_s3,
                    s3_to_db=S3ToDbScanResult(status="not_executed", warnings=[]),
                    error_detail=str(exc),
                )

        s3_to_db = S3ToDbScanResult(
            status="not_executed",
            warnings=[],
        )

        if db_to_s3.blockers or db_to_s3.status == "not_executed":
            overall_status = "fail"
        else:
            # sample completed without blockers — but orphan check was skipped
            overall_status = "scan_partial"

        return ConsistencyReport(
            scan_status=overall_status,
            db_to_s3=db_to_s3,
            s3_to_db=s3_to_db,
        )
    finally:
        await engine.dispose()


# ── URL normalisation ─────────────────────────────────────────────────────────


def _normalize_db_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ValueError("database URL is required")
    for prefix, replacement in (
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
        ("postgres://", "postgresql+asyncpg://"),
    ):
        if url.startswith(prefix):
            return url.replace(prefix, replacement, 1)
    if url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite:///")):
        return url
    raise ValueError(f"unsupported database URL scheme: {url!r}")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_SYNC"),
        help="PostgreSQL database URL (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "sample"],
        default="full",
        help=(
            "full: both DB→S3 and S3→DB directions (default). "
            "sample: DB→S3 only, up to --sample-size references."
        ),
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=int(os.getenv("STORAGE_CONSISTENCY_SAMPLE_SIZE", "10")),
        help="Number of DB references to check in sample mode (default: 10).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress human-readable output; emit only protocol lines.",
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

    if args.mode == "full":
        report = await _run_full_scan(args.database_url)
    else:
        report = await _run_sample_scan(args.database_url, args.sample_size)

    # ── emit machine-readable protocol lines ──────────────────────────────────
    blocker_count = len(report.db_to_s3.blockers)
    warning_count = len(report.s3_to_db.warnings)

    detail_parts = [f"db_to_s3={report.db_to_s3.status}"]
    if blocker_count:
        detail_parts.append(f"blockers={blocker_count}")
    detail_parts.append(f"s3_to_db={report.s3_to_db.status}")
    if warning_count:
        detail_parts.append(f"warnings={warning_count}")
    if report.error_detail:
        detail_parts.append(f"error={report.error_detail}")

    emit_scan_status(report.scan_status, " ".join(detail_parts))

    for blocker in report.db_to_s3.blockers:
        emit_blocker(blocker)

    for warning in report.s3_to_db.warnings:
        emit_warning(warning)

    emit_report_json(report)

    # ── human-readable report ─────────────────────────────────────────────────
    if not args.json_only:
        print_human_report(report, mode=args.mode, sample_size=args.sample_size if args.mode == "sample" else None)

    # ── exit code ─────────────────────────────────────────────────────────────
    if report.scan_status == "fail":
        return 1
    if report.scan_status == "scan_partial":
        return 2
    # scan_complete or warning: exit 0; caller should inspect protocol lines for warnings
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
