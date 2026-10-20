#!/usr/bin/env python3
"""N9: doplní ORM sloupcům server_default podle schématu vytvořeného migracemi.

Zdroj pravdy je produkční schéma (migration_tests/baseline/pg_schema.json) a seznam
rozdílů (migration_tests/baseline/metadata_diff.txt, řádky modify_default). Výchozí
hodnota se zapíše přenositelně (bez PostgreSQL přetypování `::type`), aby šla použít
i v SQLite (dev, `create_all`). Alembic na PostgreSQL porovnává server defaulty
vyhodnocením výrazů, takže `'queued'` == `'queued'::character varying`.

    python tools/refactor/n9_add_server_defaults.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import libcst as cst

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def portable(default: str) -> str:
    return re.sub(r"::[a-z ]+$", "", default.strip())


def targets() -> dict[Path, dict[str, dict[str, str]]]:
    from app.composition.models import import_all_models
    from app.platform.db.base import Base

    import_all_models()
    pg = json.loads((BACKEND / "migration_tests/baseline/pg_schema.json").read_text(encoding="utf-8"))
    db_defaults = {(c["table_name"], c["column_name"]): c["column_default"] for c in pg["columns"]}
    wanted: list[tuple[str, str]] = []
    for line in (BACKEND / "migration_tests/baseline/metadata_diff.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("modify_default:"):
            _, table, column, _rest = line.split(":", 3)
            wanted.append((table, column))
    out: dict[Path, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    for mapper in Base.registry.mappers:
        table = mapper.local_table.name
        module = sys.modules[mapper.class_.__module__]
        for prop in mapper.column_attrs:
            column = prop.columns[0]
            if (table, column.name) in wanted:
                out[Path(module.__file__)][mapper.class_.__name__][prop.key] = portable(
                    db_defaults[(table, column.name)]
                )
    missing = set(wanted) - {
        (m.local_table.name, p.columns[0].name)
        for m in Base.registry.mappers
        for p in m.column_attrs
        if (m.local_table.name, p.columns[0].name) in wanted
    }
    if missing:
        raise SystemExit(f"columns not found in ORM: {sorted(missing)}")
    return out


class _AddDefaults(cst.CSTTransformer):
    def __init__(self, classes: dict[str, dict[str, str]]) -> None:
        self.classes = classes
        self.current: str | None = None
        self.done: set[tuple[str, str]] = set()

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self.current = node.name.value

    def leave_ClassDef(self, original: cst.ClassDef, updated: cst.ClassDef) -> cst.ClassDef:
        self.current = None
        return updated

    def leave_AnnAssign(self, original: cst.AnnAssign, updated: cst.AnnAssign) -> cst.AnnAssign:
        attrs = self.classes.get(self.current or "")
        if not attrs or not isinstance(updated.target, cst.Name):
            return updated
        attr = updated.target.value
        if attr not in attrs or not isinstance(updated.value, cst.Call):
            return updated
        call = updated.value
        if any(arg.keyword and arg.keyword.value == "server_default" for arg in call.args):
            raise SystemExit(f"{self.current}.{attr} already has server_default")
        value = cst.parse_expression(f"text({json.dumps(attrs[attr])})")
        new_arg = cst.Arg(keyword=cst.Name("server_default"), value=value, equal=cst.AssignEqual(
            whitespace_before=cst.SimpleWhitespace(""), whitespace_after=cst.SimpleWhitespace("")))
        args = list(call.args)
        last = args[-1]
        # zachovat víceřádkové formátování: nový argument za poslední, se stejnou čárkou
        if isinstance(last.comma, cst.Comma):
            args.append(new_arg.with_changes(comma=last.comma))
            args[-2] = last
        else:
            args[-1] = last.with_changes(comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")))
            args.append(new_arg)
        self.done.add((self.current or "", attr))
        return updated.with_changes(value=call.with_changes(args=args))


def ensure_text_import(code: str) -> str:
    if re.search(r"^from sqlalchemy import [^\n(]*\btext\b", code, re.M) or re.search(
        r"^from sqlalchemy import \((?:[^)]*\n)*?\s*text,", code, re.M
    ):
        return code
    return code.replace("from sqlalchemy.orm import", "from sqlalchemy import text\nfrom sqlalchemy.orm import", 1)


def main() -> int:
    total = 0
    for path, classes in targets().items():
        module = cst.parse_module(path.read_text(encoding="utf-8"))
        transformer = _AddDefaults(classes)
        code = module.visit(transformer).code
        expected = {(c, a) for c, attrs in classes.items() for a in attrs}
        if transformer.done != expected:
            raise SystemExit(f"{path}: not applied {sorted(expected - transformer.done)}")
        path.write_text(ensure_text_import(code), encoding="utf-8")
        total += len(expected)
        print(f"{path.relative_to(BACKEND)}: {len(expected)} server_default")
    print(f"total {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
