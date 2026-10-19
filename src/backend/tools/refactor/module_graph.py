#!/usr/bin/env python3
"""Graf závislostí mezi CÍLOVÝMI moduly, spočtený ze současného kódu (vč. lokálních importů).

    python tools/refactor/module_graph.py [--detail MOD_A MOD_B]
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ownership import FILE_OWNER, SCHEMA_PROJECT_OWNER, SCHEMA_QUOTE_OWNER, SPLIT_FILES  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]


def module_name(path: Path) -> str:
    rel = path.relative_to(BACKEND).with_suffix("")
    name = ".".join(rel.parts)
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def owner_of_module(mod: str) -> str | None:
    if mod in FILE_OWNER:
        return FILE_OWNER[mod]
    if mod + ".__init__" in FILE_OWNER:
        return FILE_OWNER[mod + ".__init__"]
    return None


def owner_of_symbol(mod: str, name: str | None) -> str | None:
    if mod in SPLIT_FILES and name:
        return SPLIT_FILES[mod].get(name, "platform" if name in {"Base"} else None)
    if mod in ("app.schemas.project", "app.schemas") and name:
        if name in SCHEMA_PROJECT_OWNER:
            return SCHEMA_PROJECT_OWNER[name]
        if mod == "app.schemas" and name.startswith(("Photo", "Image", "Upload")):
            return "media"
        return "cases"
    if mod == "app.schemas.quote_variant" and name:
        return SCHEMA_QUOTE_OWNER.get(name, "quoting")
    sub = f"{mod}.{name}" if name else mod
    return owner_of_module(sub) or owner_of_module(mod)


def edges():
    out = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        mod = module_name(path)
        if mod in SPLIT_FILES or mod in ("app.schemas", "app.__init__", "app", "app.user.api"):
            continue
        src_owner = owner_of_module(mod)
        if src_owner is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        func_depth = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    func_depth[id(child)] = True
        type_checking = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                for child in ast.walk(node):
                    type_checking.add(id(child))
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
                targets = [(node.module, a.name) for a in node.names]
            elif isinstance(node, ast.Import):
                targets = [(a.name, None) for a in node.names if a.name.startswith("app")]
            for target_mod, name in targets:
                dst = owner_of_symbol(target_mod, name)
                if dst is None or dst == src_owner:
                    continue
                kind = "typing" if id(node) in type_checking else ("lazy" if id(node) in func_depth else "top")
                out.append((src_owner, dst, kind, f"{mod}:{node.lineno} {target_mod}.{name or ''}"))
    return out


def main() -> int:
    all_edges = edges()
    if len(sys.argv) > 2 and sys.argv[1] == "--detail":
        for a, b, kind, where in all_edges:
            if a == sys.argv[2] and b == sys.argv[3]:
                print(kind, where)
        return 0
    agg = defaultdict(lambda: defaultdict(int))
    for a, b, kind, _ in all_edges:
        agg[(a, b)][kind] += 1
    for (a, b), kinds in sorted(agg.items()):
        print(f"{a:12} -> {b:12} " + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
