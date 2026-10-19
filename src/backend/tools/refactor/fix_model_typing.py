#!/usr/bin/env python3
"""Doplní `if TYPE_CHECKING:` importy pro jména ve stringových anotacích ORM relací.

Relace mezi modely různých modulů se deklarují stringem (`Mapped["Project"]`),
SQLAlchemy je resolvuje za běhu přes registr – runtime import není potřeba.
Pro ruff/mypy se jména importují jen pod TYPE_CHECKING (bez runtime vazby).

    python tools/refactor/fix_model_typing.py app/modules/identity/models.py ...
"""
from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
IDENT = re.compile(r"[A-Za-z_]\w*")
_BUILTINS = {"list", "dict", "set", "tuple", "None", "str", "int", "float", "bool", "Any", "Optional"}


def _class_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for path in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        module = ".".join(path.relative_to(BACKEND).with_suffix("").parts)
        is_model_module = module.endswith(".models") or module.startswith("app.models")
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                # ORM modely mají přednost před stejnojmennými Pydantic schématy
                if is_model_module or node.name not in index:
                    index[node.name] = module
    return index


def _needed(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            for sub in ast.walk(node.annotation):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    names.update(IDENT.findall(sub.value))
    return names - _BUILTINS


def _available(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


def fix(path: Path, index: dict[str, str]) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    own_module = ".".join(path.relative_to(BACKEND).with_suffix("").parts)
    missing = sorted(_needed(tree) - _available(tree))
    by_module: dict[str, list[str]] = defaultdict(list)
    for name in missing:
        module = index.get(name)
        if module and module != own_module:
            by_module[module].append(name)
    if not by_module:
        return False
    block = "if TYPE_CHECKING:\n" + "".join(
        f"    from {module} import {', '.join(names)}\n" for module, names in sorted(by_module.items())
    )
    lines = source.splitlines(keepends=True)
    last_import = max(
        node.end_lineno or node.lineno for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    has_tc = any(
        isinstance(n, ast.ImportFrom) and n.module == "typing" and any(a.name == "TYPE_CHECKING" for a in n.names)
        for n in tree.body
    )
    insert = ("" if has_tc else "from typing import TYPE_CHECKING\n") + "\n" + block
    lines.insert(last_import, insert)
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    index = _class_index()
    for raw in sys.argv[1:]:
        if fix(BACKEND / raw, index):
            print("typing imports added:", raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
