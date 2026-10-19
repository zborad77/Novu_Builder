"""Hranice modulů backendu (modulární monolit).

Pravidla (docs/architecture/MODULAR_ARCHITECTURE.md):
  R1  Z jiného modulu se importuje výhradně `app.modules.<modul>.public`.
  R1b Přes hranici modulu se neimportují privátní jména (`_x`).
  R2  Závislosti jen směrem dolů podle vrstev – kontroluje import-linter
      (`[tool.importlinter]` v pyproject.toml), včetně zákazu cyklů.
  R3  `app.platform` nezná doménové moduly ani kompoziční vrstvu.
  R4  Staré vrstvené balíčky (app.services, app.repositories, …) neexistují.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP = BACKEND_ROOT / "app"

LEGACY_PACKAGES = (
    "ai", "api", "case_workflow", "core", "db", "models", "offer_processing",
    "repositories", "schemas", "services", "storage", "work_catalog",
)


def _module_of(path: Path) -> str:
    name = ".".join(path.relative_to(BACKEND_ROOT).with_suffix("").parts)
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _owner(module: str) -> str | None:
    parts = module.split(".")
    return parts[2] if len(parts) >= 3 and parts[:2] == ["app", "modules"] else None


def _imports():
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        importer = _module_of(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and not node.level and node.module:
                yield importer, node.module, [a.name for a in node.names], node.lineno
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    yield importer, alias.name, [], node.lineno


def test_cross_module_imports_go_through_public_api():
    violations = []
    for importer, target, names, line in _imports():
        target_owner = _owner(target)
        if target_owner is None or target_owner == _owner(importer):
            continue
        if target != f"app.modules.{target_owner}.public" or not names:
            violations.append(f"{importer}:{line} imports {target}")
    assert not violations, "R1 – použij app.modules.<modul>.public:\n" + "\n".join(violations)


def test_no_private_names_cross_module_boundaries():
    violations = []
    for importer, target, names, line in _imports():
        target_owner = _owner(target)
        if target_owner is None or target_owner == _owner(importer):
            continue
        private = [n for n in names if n.startswith("_")]
        if private:
            violations.append(f"{importer}:{line} imports private {private} from {target}")
    assert not violations, "R1b:\n" + "\n".join(violations)


def test_platform_does_not_depend_on_domain_or_composition():
    forbidden = ("app.modules", "app.composition", "app.worker", "app.main")
    violations = [
        f"{importer}:{line} imports {target}"
        for importer, target, _names, line in _imports()
        if importer.startswith("app.platform") and target.startswith(forbidden)
    ]
    assert not violations, "R3:\n" + "\n".join(violations)


def test_legacy_layered_packages_are_gone():
    leftovers = [name for name in LEGACY_PACKAGES if (APP / name).exists() and any((APP / name).rglob("*.py"))]
    assert not leftovers, f"R4 – staré balíčky stále obsahují kód: {leftovers}"


def test_import_linter_layers_and_acyclicity():
    result = subprocess.run(
        [sys.executable, "-c", "from importlinter.cli import lint_imports_command; lint_imports_command()"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-2000:]
