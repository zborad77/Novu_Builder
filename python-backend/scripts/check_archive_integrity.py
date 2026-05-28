#!/usr/bin/env python
"""
Archive integrity checker for proposal-archive-zip exports.

Checks:
  - Required files present (proposal_snapshot.json, timeline.json)
  - archiveSchemaVersion present in each JSON file
  - timeline.json uses versioned envelope format (not raw list)
  - Proposal fields valid (id, status, draftVersion)
  - pricing_snapshot.json present when inputVersions.pricingProfileSnapshot is set
  - Lineage: analysisResultId in proposal matches an analysis.completed event in timeline
  - manifest.json SHA-256 hashes match actual file contents (when manifest present)

Exit codes:
  0  all checks pass
  1  warnings only (non-critical issues)
  2  errors (blocking issues) or bad arguments
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile, ZipFile

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
REQUIRED_FILES = ("proposal_snapshot.json", "timeline.json")


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check_archive(zip_path: Path) -> CheckResult:
    result = CheckResult()

    try:
        zf = ZipFile(zip_path, "r")
    except BadZipFile as exc:
        result.errors.append(f"not_a_valid_zip: {exc}")
        return result
    except FileNotFoundError:
        result.errors.append(f"file_not_found: {zip_path}")
        return result

    with zf:
        names = set(zf.namelist())

        # 1. Required files
        for required in REQUIRED_FILES:
            if required not in names:
                result.errors.append(f"missing_required_file: {required}")

        # 2. Parse proposal_snapshot.json
        proposal: dict | None = None
        if "proposal_snapshot.json" in names:
            try:
                proposal = json.loads(zf.read("proposal_snapshot.json"))
            except json.JSONDecodeError as exc:
                result.errors.append(f"proposal_snapshot_invalid_json: {exc}")

            if proposal is not None:
                schema_ver = proposal.get("archiveSchemaVersion")
                if schema_ver is None:
                    result.errors.append("proposal_snapshot_missing_schema_version")
                elif schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
                    result.warnings.append(f"proposal_snapshot_unknown_schema_version: {schema_ver}")

                for required_field in ("id", "status", "draftVersion"):
                    if proposal.get(required_field) is None:
                        result.errors.append(f"proposal_snapshot_missing_field: {required_field}")

                input_versions = proposal.get("inputVersions") or {}
                if input_versions.get("pricingProfileSnapshot") and "pricing_snapshot.json" not in names:
                    result.warnings.append(
                        "pricing_snapshot_missing_but_expected: inputVersions.pricingProfileSnapshot is set"
                    )

        # 3. Parse timeline.json
        timeline_events: list[dict] = []
        if "timeline.json" in names:
            try:
                timeline_raw = json.loads(zf.read("timeline.json"))
            except json.JSONDecodeError as exc:
                result.errors.append(f"timeline_invalid_json: {exc}")
                timeline_raw = None

            if timeline_raw is not None:
                if isinstance(timeline_raw, list):
                    # Pre-versioning format — root was a raw list
                    result.errors.append(
                        "timeline_unversioned_format: root is a list, expected {archiveSchemaVersion, events}"
                    )
                elif isinstance(timeline_raw, dict):
                    schema_ver = timeline_raw.get("archiveSchemaVersion")
                    if schema_ver is None:
                        result.errors.append("timeline_missing_schema_version")
                    elif schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
                        result.warnings.append(f"timeline_unknown_schema_version: {schema_ver}")

                    events = timeline_raw.get("events")
                    if not isinstance(events, list):
                        result.errors.append("timeline_events_not_a_list")
                    else:
                        timeline_events = events
                        if not events and proposal is not None:
                            result.warnings.append("timeline_empty_but_proposal_exists")
                else:
                    result.errors.append(f"timeline_unexpected_root_type: {type(timeline_raw).__name__}")

        # 4. Parse pricing_snapshot.json if present
        if "pricing_snapshot.json" in names:
            try:
                pricing = json.loads(zf.read("pricing_snapshot.json"))
            except json.JSONDecodeError as exc:
                result.errors.append(f"pricing_snapshot_invalid_json: {exc}")
                pricing = None

            if pricing is not None:
                schema_ver = pricing.get("archiveSchemaVersion")
                if schema_ver is None:
                    result.errors.append("pricing_snapshot_missing_schema_version")
                elif schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
                    result.warnings.append(f"pricing_snapshot_unknown_schema_version: {schema_ver}")

        # 5. Lineage: analysisResultId in proposal → analysis.completed event in timeline
        if proposal is not None and timeline_events:
            analysis_result_id = proposal.get("analysisResultId")
            if analysis_result_id:
                completed_ids = {
                    evt.get("payload", {}).get("analysis_result_id")
                    for evt in timeline_events
                    if isinstance(evt, dict) and evt.get("eventType") == "analysis.completed"
                }
                if analysis_result_id not in completed_ids:
                    result.warnings.append(
                        f"lineage_analysis_result_not_in_timeline: analysisResultId={analysis_result_id}"
                    )

        # 6. Manifest hash verification (when manifest.json is present)
        if "manifest.json" in names:
            try:
                manifest = json.loads(zf.read("manifest.json"))
            except json.JSONDecodeError as exc:
                result.errors.append(f"manifest_invalid_json: {exc}")
                manifest = None

            if manifest is not None:
                schema_ver = manifest.get("archiveSchemaVersion")
                if schema_ver is None:
                    result.errors.append("manifest_missing_schema_version")
                elif schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
                    result.warnings.append(f"manifest_unknown_schema_version: {schema_ver}")

                file_hashes: dict = manifest.get("files") or {}
                for fname, expected_hash in file_hashes.items():
                    if fname not in names:
                        result.errors.append(f"manifest_references_missing_file: {fname}")
                        continue
                    if not isinstance(expected_hash, str) or not expected_hash.startswith("sha256:"):
                        result.warnings.append(f"manifest_unrecognised_hash_format: {fname}={expected_hash!r}")
                        continue
                    expected_hex = expected_hash[len("sha256:"):]
                    actual_hex = hashlib.sha256(zf.read(fname)).hexdigest()
                    if actual_hex != expected_hex:
                        result.errors.append(
                            f"manifest_hash_mismatch: {fname} expected={expected_hex[:16]}… got={actual_hex[:16]}…"
                        )

    return result


def _sanitize(v: str) -> str:
    return " ".join(v.replace("|", "/").split())


def _emit(tag: str, *fields: str) -> None:
    print("|".join([tag] + [_sanitize(f) for f in fields]))


def _print_human_report(zip_path: Path, result: CheckResult) -> None:
    sep = "=" * 60
    print(sep)
    print("Archive Integrity Report")
    print(sep)
    print(f"  Archive: {zip_path}")
    if not result.errors and not result.warnings:
        print("  Status:  OK — all checks passed")
    elif result.errors:
        print(f"  Status:  FAIL — {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    else:
        print(f"  Status:  WARNING — {len(result.warnings)} warning(s)")
    print()

    if result.errors:
        print(f"  ERRORS ({len(result.errors)}):")
        for err in result.errors:
            print(f"    [ERROR] {err}")
        print()

    if result.warnings:
        print(f"  WARNINGS ({len(result.warnings)}):")
        for warn in result.warnings:
            print(f"    [WARN]  {warn}")
        print()

    print(sep)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Path to the proposal-archive-zip file")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Emit only machine-readable protocol lines (no human report)",
    )
    args = parser.parse_args()

    if not args.archive:
        print("ERROR: archive path is required", file=sys.stderr)
        return 2

    result = _check_archive(args.archive)

    status = "ok" if not result.errors and not result.warnings else ("fail" if result.errors else "warning")
    _emit("ARCHIVE_INTEGRITY_STATUS", str(args.archive), status)
    for err in result.errors:
        _emit("ARCHIVE_INTEGRITY_ERROR", str(args.archive), err)
    for warn in result.warnings:
        _emit("ARCHIVE_INTEGRITY_WARNING", str(args.archive), warn)

    report_json = {
        "archive": str(args.archive),
        "status": status,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
        "errors": result.errors,
        "warnings": result.warnings,
    }
    print("ARCHIVE_INTEGRITY_REPORT_JSON=" + json.dumps(report_json, separators=(",", ":"), sort_keys=True))

    if not args.json_only:
        _print_human_report(args.archive, result)

    if result.errors:
        return 2
    if result.warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
