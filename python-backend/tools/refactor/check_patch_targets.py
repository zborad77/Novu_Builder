#!/usr/bin/env python3
"""Statická kontrola stringových cílů mocků v testech (modulární refaktor).

Pro každý `patch("app.x.NAME")` / `monkeypatch.setattr("app.x.NAME", ...)` ověří:
  * modul `app.x` existuje a atribut NAME v něm existuje (jinak by patch selhal),
  * NAME je v modulu skutečně použit (Load) nebo v něm definován.
Cíl, který je v modulu jen importován a nikde nepoužit, je NEÚČINNÝ: mock
nezmění chování kódu, který se testuje.

Výstup: JSON se seznamem cílů a jejich klasifikací; `--max-ineffective N`
selže, pokud počet neúčinných cílů přesáhne N (baseline).

    python tools/refactor/check_patch_targets.py --json out.json --max-ineffective 0
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET_RE = re.compile(r"^app(\.[A-Za-z_]\w*)+$")


def _module_file(module: str) -> Path | None:
    rel = Path(*module.split("."))
    for candidate in (BACKEND / rel.with_suffix(".py"), BACKEND / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _split(target: str) -> tuple[str, str] | None:
    parts = target.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:cut])
        if _module_file(module) is not None:
            return module, parts[cut]
    return None


_CACHE: dict[Path, tuple[set[str], set[str], set[str]]] = {}


def _names(path: Path) -> tuple[set[str], set[str], set[str]]:
    if path not in _CACHE:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        loaded, defined, imported = set(), set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loaded.add(node.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined.add(node.target.id)
        _CACHE[path] = (loaded, defined, imported)
    return _CACHE[path]


def _targets(test_file: Path):
    tree = ast.parse(test_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in {"patch", "setattr", "setitem"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) and TARGET_RE.match(first.value):
            yield first.value, node.lineno


def classify(target: str) -> str:
    split = _split(target)
    if split is None:
        return "missing-module"
    module, attribute = split
    path = _module_file(module)
    assert path is not None
    loaded, defined, imported = _names(path)
    if attribute in loaded:
        return "used"
    if attribute in defined:
        return "defined"
    if attribute in imported:
        return "ineffective-import-only"
    # submodul (patch "app.x.submodule") nebo atribut vytvořený dynamicky
    if _module_file(f"{module}.{attribute}") is not None:
        return "submodule"
    return "missing-attribute"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", default=str(BACKEND / "tests"))
    parser.add_argument("--json")
    parser.add_argument("--max-ineffective", type=int)
    args = parser.parse_args()
    rows = []
    for test_file in sorted(Path(args.tests).rglob("test*.py")):
        for target, line in _targets(test_file):
            rows.append(
                {"file": test_file.name, "line": line, "target": target, "status": classify(target)}
            )
    summary: dict[str, int] = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "targets": rows}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    bad = [r for r in rows if r["status"] in {"ineffective-import-only", "missing-module", "missing-attribute"}]
    for row in bad:
        print(f"{row['status']:26} {row['file']}:{row['line']}  {row['target']}")
    if args.max_ineffective is not None and len(bad) > args.max_ineffective:
        print(f"FAIL: {len(bad)} > baseline {args.max_ineffective}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
