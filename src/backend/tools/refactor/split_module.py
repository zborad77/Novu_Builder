#!/usr/bin/env python3
"""Rozdělí modul: přesune top-level definice (třídy, funkce, konstanty) do jiných souborů.

Definice se přesouvají doslova (včetně dekorátorů a komentářů těsně nad nimi).
Nový soubor dostane kopii importní hlavičky zdroje; nepoužité importy pak odstraní
`ruff check --select F401 --fix` (spouští se automaticky na dotčené soubory).

Plán (JSON):
    {"source": "app/models/domain.py",
     "moves": {"app/modules/identity/models.py": ["Organization", "User"], ...},
     "header": "\"\"\"Docstring nového souboru.\"\"\"\n"}   # volitelné

    python tools/refactor/split_module.py plan.json
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _definition_spans(source: str) -> dict[str, tuple[int, int]]:
    """name -> (start_line, end_line) 1-based inclusive, včetně dekorátorů a komentářů nad definicí."""
    tree = ast.parse(source)
    lines = source.splitlines()
    spans: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [node.name]
            start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            start = node.lineno
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
            start = node.lineno
        else:
            continue
        # komentáře bezprostředně nad definicí patří k ní
        while start > 1 and lines[start - 2].lstrip().startswith("#"):
            start -= 1
        end = node.end_lineno or node.lineno
        for name in names:
            spans[name] = (start, end)
    return spans


def _header(source: str) -> str:
    """Docstring + importy + `from __future__` z hlavičky zdroje (vše před první definicí)."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.extend(lines[node.lineno - 1 : node.end_lineno])
        elif isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            out.extend(lines[node.lineno - 1 : node.end_lineno])
    return "".join(out)


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    src_path = BACKEND / plan["source"]
    source = src_path.read_text(encoding="utf-8")
    spans = _definition_spans(source)
    lines = source.splitlines(keepends=True)
    header = _header(source)
    removed: set[int] = set()
    touched: list[Path] = []
    for dest_rel, names in plan["moves"].items():
        dest = BACKEND / dest_rel
        chunks = []
        for name in names:
            if name not in spans:
                raise SystemExit(f"{name} not found in {plan['source']}")
            start, end = spans[name]
            chunks.append("".join(lines[start - 1 : end]).rstrip("\n") + "\n")
            removed.update(range(start, end + 1))
        body = "\n\n".join(chunks)
        if dest.exists():
            dest.write_text(dest.read_text(encoding="utf-8").rstrip("\n") + "\n\n\n" + body, encoding="utf-8")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            doc = plan.get("headers", {}).get(dest_rel, "")
            dest.write_text(doc + header + "\n\n" + body, encoding="utf-8")
        touched.append(dest)
    remaining = "".join(line for i, line in enumerate(lines, start=1) if i not in removed)
    # zredukovat vícenásobné prázdné řádky vzniklé vyjmutím
    while "\n\n\n\n" in remaining:
        remaining = remaining.replace("\n\n\n\n", "\n\n\n")
    src_path.write_text(remaining, encoding="utf-8")
    touched.append(src_path)
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "F401", "--fix", "-q", *map(str, touched)],
        cwd=BACKEND,
        check=False,
    )
    for path in touched:
        print("wrote", path.relative_to(BACKEND))
    return 0


if __name__ == "__main__":
    sys.exit(main())
