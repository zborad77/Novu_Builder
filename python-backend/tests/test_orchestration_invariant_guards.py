from __future__ import annotations

import re
from pathlib import Path

from app.case_orchestration.orchestration_dispatch_registry import (
    DISPATCH_REGISTRY,
    INFRASTRUCTURE_ONLY_DISPATCH_NAMES,
    ORCHESTRATION_OWNED_DISPATCH_NAMES,
    SANCTIONED_DISPATCH_CALL_SITES,
    SANCTIONED_DISPATCH_NAMES,
    SANCTIONED_DISPATCH_PATHS,
)

APP_ROOT = Path("python-backend/app")
ALLOWLIST_DOC = Path("docs/orchestration_dispatch_allowlist.md")


def _python_sources() -> list[Path]:
    return sorted(path for path in APP_ROOT.rglob("*.py") if path.is_file())


def test_no_enqueue_outside_orchestrator() -> None:
    queue_call_pattern = re.compile(r"\b(?:enqueue_analysis_job|enqueue_heavy_job)\(")
    violations: list[str] = []

    for path in _python_sources():
        normalized = path.as_posix()
        if normalized in SANCTIONED_DISPATCH_PATHS:
            continue
        source = path.read_text(encoding="utf-8")
        if queue_call_pattern.search(source):
            violations.append(normalized)

    assert not violations, f"Direct queue enqueue call leaked outside sanctioned dispatch points: {violations}"


def test_no_direct_status_write() -> None:
    status_write_pattern = re.compile(r"\b(?:project|case)\.status\s*=(?!=)")
    violations: list[str] = []

    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        if status_write_pattern.search(source):
            violations.append(path.as_posix())

    assert not violations, f"Direct case status writes remain in app/: {violations}"


def test_quote_recalculation_trigger_only_flows_via_command_path() -> None:
    direct_trigger_pattern = re.compile(r"\benqueue_quote_recalculation_job\(")
    violations: list[str] = []
    occurrences_in_analysis_service = 0

    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        matches = direct_trigger_pattern.findall(source)
        if not matches:
            continue
        if path.as_posix() == "python-backend/app/services/analysis_service.py":
            occurrences_in_analysis_service = len(matches)
            continue
        violations.append(path.as_posix())

    assert not violations, f"Direct quote recalculation trigger leaked outside analysis service wrapper: {violations}"
    assert occurrences_in_analysis_service == 1


def test_dispatch_registry_documents_every_sanctioned_dispatch_point() -> None:
    allowlist_doc = ALLOWLIST_DOC.read_text(encoding="utf-8")

    for dispatch_name, point in DISPATCH_REGISTRY.items():
        assert dispatch_name in allowlist_doc, f"Dispatch allowlist doc is missing {dispatch_name}"
        assert point.description in allowlist_doc

    for path in SANCTIONED_DISPATCH_CALL_SITES:
        assert path in allowlist_doc, f"Dispatch allowlist doc is missing sanctioned call site {path}"


def test_dispatch_registry_categories_remain_explicit_and_non_empty() -> None:
    assert SANCTIONED_DISPATCH_NAMES == frozenset(DISPATCH_REGISTRY)
    assert INFRASTRUCTURE_ONLY_DISPATCH_NAMES
    assert ORCHESTRATION_OWNED_DISPATCH_NAMES
    assert INFRASTRUCTURE_ONLY_DISPATCH_NAMES.isdisjoint(ORCHESTRATION_OWNED_DISPATCH_NAMES)
