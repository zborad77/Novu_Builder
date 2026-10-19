#!/usr/bin/env python3
"""Vygeneruje `public.py` každého modulu a přepíše importy mezi moduly na `.public`.

1. Najde všechny importy `from app.modules.<B>.<cokoli> import X`, jejichž importér
   NENÍ uvnitř modulu B (jiný modul, composition, worker, main). Importy pod
   TYPE_CHECKING se počítají také.
2. Pro každý modul B vygeneruje `app/modules/<B>/public.py`, který tyto symboly
   explicitně re-exportuje (`__all__`). Ručně doplněné řádky mezi značkami
   `# --- ručně ---` se zachovají.
3. Přepíše dotčené importy na `from app.modules.<B>.public import X`.

Testy (tests/) a skripty se nepřepisují – smí sahat do vnitřků modulů.

    python tools/refactor/make_public.py [--check]
"""
from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

import libcst as cst
from libcst.helpers import get_full_name_for_node

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"


def module_of(path: Path) -> str:
    rel = path.relative_to(BACKEND).with_suffix("")
    name = ".".join(rel.parts)
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def owner(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "modules"]:
        return parts[2]
    return None


def collect() -> dict[str, dict[str, set[str]]]:
    """modul B -> {interní modul -> {symboly}} importované zvenku."""
    exports: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        importer = module_of(path)
        importer_owner = owner(importer)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            target_owner = owner(node.module)
            if target_owner is None or target_owner == importer_owner:
                continue
            if node.module == f"app.modules.{target_owner}.public":
                continue
            for alias in node.names:
                exports[target_owner][node.module].add(alias.name)
    return exports


def render_public(module: str, symbols: dict[str, set[str]], previous: str | None) -> str:
    manual = ""
    if previous and "# --- ručně ---" in previous:
        manual = previous[previous.index("# --- ručně ---") :].split("# --- konec ---")[0] + "# --- konec ---\n"
    names: list[str] = []
    lines = [
        f'"""Veřejné rozhraní modulu {module}.\n\n'
        "Ostatní moduly, composition a worker smějí z tohoto modulu importovat\n"
        "výhradně odsud (vynucuje tests/architecture/test_module_boundaries.py).\n"
        "Vygenerováno tools/refactor/make_public.py; ruční doplňky patří mezi značky\n"
        '`# --- ručně ---` a `# --- konec ---`.\n"""\n',
    ]
    for internal in sorted(symbols):
        syms = sorted(symbols[internal])
        names.extend(syms)
        joined = ",\n    ".join(syms)
        lines.append(f"from {internal} import (  # noqa: F401\n    {joined},\n)\n")
    text = "".join(lines)
    if manual:
        text += "\n" + manual
    all_names = sorted(set(names))
    text += "\n__all__ = [\n" + "".join(f'    "{n}",\n' for n in all_names) + "]\n"
    return text


class _Rewriter(cst.CSTTransformer):
    def __init__(self, importer_owner: str | None) -> None:
        self.importer_owner = importer_owner
        self.changed = False

    def leave_ImportFrom(self, original: cst.ImportFrom, updated: cst.ImportFrom) -> cst.ImportFrom:
        if updated.relative or updated.module is None:
            return updated
        name = get_full_name_for_node(updated.module) or ""
        target_owner = owner(name)
        if target_owner is None or target_owner == self.importer_owner:
            return updated
        public = f"app.modules.{target_owner}.public"
        if name == public:
            return updated
        self.changed = True
        return updated.with_changes(module=cst.parse_expression(public))


def rewrite_importers(check: bool) -> list[str]:
    changed = []
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "public.py":
            continue
        source = path.read_text(encoding="utf-8")
        rewriter = _Rewriter(owner(module_of(path)))
        result = cst.parse_module(source).visit(rewriter)
        if rewriter.changed:
            changed.append(str(path.relative_to(BACKEND)))
            if not check:
                path.write_bytes(result.code.encode("utf-8"))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="jen vypsat, nic nezapisovat")
    args = parser.parse_args()
    exports = collect()
    for module, symbols in sorted(exports.items()):
        target = APP / "modules" / module / "public.py"
        previous = target.read_text(encoding="utf-8") if target.exists() else None
        # zachovat i dříve exportované symboly (public API se nezužuje automaticky)
        if previous:
            tree = ast.parse(previous)
            for node in tree.body:
                if isinstance(node, ast.ImportFrom) and node.module and owner(node.module) == module:
                    for alias in node.names:
                        symbols[node.module].add(alias.name)
        text = render_public(f"app.modules.{module}", symbols, previous)
        print(f"public.py {module}: {sum(len(v) for v in symbols.values())} symbolů")
        if not args.check:
            target.write_text(text, encoding="utf-8")
    changed = rewrite_importers(args.check)
    print(f"{len(changed)} importérů {'k přepsání' if args.check else 'přepsáno'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
