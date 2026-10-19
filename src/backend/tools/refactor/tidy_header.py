#!/usr/bin/env python3
"""Uspořádá hlavičku souboru vzniklého dělením modulu: docstring, importy po skupinách
(__future__, stdlib, third-party, app), neprázdný TYPE_CHECKING blok, pak tělo.

Mění jen importní hlavičku; definice zůstávají beze změny.

    python tools/refactor/tidy_header.py app/modules/cases/models.py ...
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _group(node: ast.stmt) -> int:
    root = (node.module if isinstance(node, ast.ImportFrom) else node.names[0].name) or ""
    root = root.split(".")[0]
    if root == "__future__":
        return 0
    if root in sys.stdlib_module_names:
        return 1
    if root == "app":
        return 3
    return 2


def tidy(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    docstring = ""
    body_start = 0
    imports: list[ast.stmt] = []
    tc_imports: list[str] = []
    for index, node in enumerate(tree.body):
        if index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        ):
            docstring = "".join(lines[node.lineno - 1 : node.end_lineno])
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(node)
            continue
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            for sub in node.body:
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    tc_imports.append("    " + ast.unparse(sub) + "\n")
            continue
        body_start = node.lineno
        # komentáře nad první definicí patří k tělu
        while body_start > 1 and lines[body_start - 2].lstrip().startswith("#"):
            body_start -= 1
        break
    groups: dict[int, list[str]] = {}
    for node in imports:
        text = "".join(lines[node.lineno - 1 : node.end_lineno])
        groups.setdefault(_group(node), []).append(text)
    if not tc_imports:
        groups[1] = [g for g in groups.get(1, []) if g.strip() != "from typing import TYPE_CHECKING"]
    parts = [docstring] if docstring else []
    for key in sorted(groups):
        if groups[key]:
            parts.append("".join(groups[key]))
    if tc_imports:
        parts.append("if TYPE_CHECKING:\n" + "".join(tc_imports))
    header = "\n".join(part.rstrip("\n") + "\n" for part in parts)
    body = "".join(lines[body_start - 1 :]) if body_start else ""
    path.write_text(header + "\n\n" + body.lstrip("\n"), encoding="utf-8")


def main() -> int:
    for raw in sys.argv[1:]:
        tidy(BACKEND / raw)
        print("tidied", raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
