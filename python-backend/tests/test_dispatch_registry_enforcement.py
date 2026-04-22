from __future__ import annotations

import ast
from pathlib import Path

from app.case_orchestration.orchestration_dispatch_registry import (
    DISPATCH_REGISTRY,
    SANCTIONED_DISPATCH_CALL_SITES,
)


PROJECT_ROOT = Path("python-backend/app")
ENQUEUE_FUNCTION_NAMES = {"enqueue_analysis_job", "enqueue_heavy_job"}


def _called_function_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _dispatch_name_keyword(node: ast.Call) -> str | None:
    for keyword in node.keywords:
        if keyword.arg != "dispatch_name":
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def test_all_dispatch_calls_are_registered() -> None:
    violations: list[str] = []

    for py_file in sorted(PROJECT_ROOT.rglob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        normalized = py_file.as_posix()
        allowed_dispatch_names = SANCTIONED_DISPATCH_CALL_SITES.get(normalized, frozenset())

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function_name = _called_function_name(node)
            if function_name not in ENQUEUE_FUNCTION_NAMES:
                continue

            dispatch_name = _dispatch_name_keyword(node)
            if dispatch_name is None:
                violations.append(
                    f"{normalized}:{getattr(node, 'lineno', '?')} missing dispatch_name"
                )
                continue
            if dispatch_name not in DISPATCH_REGISTRY:
                violations.append(
                    f"{normalized}:{getattr(node, 'lineno', '?')} unknown dispatch {dispatch_name!r}"
                )
                continue
            if dispatch_name not in allowed_dispatch_names:
                violations.append(
                    f"{normalized}:{getattr(node, 'lineno', '?')} unauthorized dispatch {dispatch_name!r}"
                )

    assert not violations, f"Unregistered or unauthorized dispatch calls: {violations}"
