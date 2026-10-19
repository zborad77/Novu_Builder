#!/usr/bin/env python3
"""Codemod modulárního refaktoru: přepíše odkazy na přesunuté moduly a symboly.

Mapa (JSON):
    {
      "modules":  {"app.core.config": "app.platform.config", ...},      # celé moduly / balíčky (prefix)
      "symbols":  {"app.models": {"User": "app.modules.identity.models", ...}, ...}  # dělené moduly
    }

Přepisuje:
  * `from X import a, b` (včetně rozdělení podle vlastníka symbolu a importu submodulů),
  * `import X` / `import X as y` a tečkové výrazy `X.attr` v kódu,
  * stringové literály obsahující tečkové cesty (cíle `patch()`, `monkeypatch.setattr()`,
    `sys.modules[...]`, `python -m ...`),
  * ne-Python soubory předané přes --text (pyproject.toml, compose, systemd …).

Nikdy nemění logiku – jen jména modulů. Po běhu je nutné spustit testy a
tools/refactor/check_patch_targets.py.

    python tools/refactor/codemod.py --map stage.json [--text FILE ...] PATH...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import libcst as cst
from libcst.helpers import get_full_name_for_node


class Mapping:
    def __init__(self, data: dict) -> None:
        self.modules: dict[str, str] = data.get("modules", {})
        self.symbols: dict[str, dict[str, str]] = data.get("symbols", {})
        # nejdelší prefix vyhrává
        self._prefixes = sorted(self.modules, key=len, reverse=True)
        names = sorted(
            set(self.modules) | {f"{m}.{s}" for m, syms in self.symbols.items() for s in syms},
            key=len,
            reverse=True,
        )
        self._text_re = (
            re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])")
            if names
            else None
        )

    def module(self, name: str) -> str:
        for prefix in self._prefixes:
            if name == prefix or name.startswith(prefix + "."):
                return self.modules[prefix] + name[len(prefix):]
        return name

    def dotted(self, name: str) -> str:
        """Plná tečková cesta (modul nebo modul.symbol...) -> nová cesta."""
        parts = name.split(".")
        for cut in range(len(parts), 0, -1):
            head = ".".join(parts[:cut])
            if head in self.symbols and cut < len(parts):
                owner = self.symbols[head].get(parts[cut])
                if owner:
                    return ".".join([owner, *parts[cut:]])
        return self.module(name)

    def text(self, value: str) -> str:
        if self._text_re is None:
            return value
        return self._text_re.sub(lambda m: self.dotted(m.group(1)), value)


def _attr_from_dotted(dotted: str) -> cst.BaseExpression:
    return cst.parse_expression(dotted)


def _module_expr(dotted: str) -> cst.Attribute | cst.Name:
    expr = cst.parse_expression(dotted)
    assert isinstance(expr, (cst.Attribute, cst.Name))
    return expr


class Rewriter(cst.CSTTransformer):
    def __init__(self, mapping: Mapping) -> None:
        self.m = mapping
        self.changed = False
        self.imported_modules: set[str] = set()  # `import app.x.y` bez aliasu

    # --- import X / import X as y -------------------------------------------------
    def leave_Import(self, original: cst.Import, updated: cst.Import) -> cst.Import:
        names = []
        for alias in updated.names:
            old = get_full_name_for_node(alias.name) or ""
            new = self.m.module(old)
            if new != old:
                self.changed = True
                if alias.asname is None:
                    self.imported_modules.add(old)
                alias = alias.with_changes(name=_module_expr(new))
            names.append(alias)
        return updated.with_changes(names=names)

    # --- from X import ... --------------------------------------------------------
    def leave_SimpleStatementLine(
        self, original: cst.SimpleStatementLine, updated: cst.SimpleStatementLine
    ) -> cst.SimpleStatementLine | cst.FlattenSentinel:
        if len(updated.body) != 1 or not isinstance(updated.body[0], cst.ImportFrom):
            return updated
        node = updated.body[0]
        if node.relative or node.module is None or isinstance(node.names, cst.ImportStar):
            if node.module is not None and not node.relative:
                old = get_full_name_for_node(node.module) or ""
                new = self.m.module(old)
                if new != old:
                    self.changed = True
                    return updated.with_changes(body=[node.with_changes(module=_module_expr(new))])
            return updated
        old_module = get_full_name_for_node(node.module) or ""
        planned: list[tuple[str, cst.ImportAlias]] = []
        for alias in node.names:
            name = get_full_name_for_node(alias.name) or ""
            target_module = self.m.module(old_module)
            if old_module in self.m.symbols and name in self.m.symbols[old_module]:
                target_module = self.m.symbols[old_module][name]
            elif f"{old_module}.{name}" in self.m.modules:
                # from pkg import submodule  -> from newpkg import newname [as submodule]
                new_full = self.m.module(f"{old_module}.{name}")
                target_module, _, new_name = new_full.rpartition(".")
                if new_name != name:
                    asname = alias.asname or cst.AsName(name=cst.Name(name))
                    alias = alias.with_changes(name=cst.Name(new_name), asname=asname)
            planned.append((target_module, alias))
        targets = list(dict.fromkeys(module for module, _ in planned))
        if targets == [old_module] and all(a is b for (_, a), b in zip(planned, node.names)):
            return updated
        self.changed = True
        if len(targets) == 1:
            # jen jiný modul: formátování (závorky, čárky, komentáře) zůstává
            return updated.with_changes(
                body=[node.with_changes(module=_module_expr(targets[0]), names=[a for _, a in planned])]
            )
        statements = []
        for index, module in enumerate(targets):
            aliases = [
                a.with_changes(comma=cst.MaybeSentinel.DEFAULT) for m, a in planned if m == module
            ]
            new_node = node.with_changes(module=_module_expr(module), names=aliases, lpar=None, rpar=None)
            statements.append(
                updated.with_changes(
                    body=[new_node],
                    leading_lines=updated.leading_lines if index == 0 else [],
                )
            )
        return cst.FlattenSentinel(statements)

    # --- app.x.y.attr ve výrazech (po `import app.x.y`) -----------------------------
    def leave_Attribute(self, original: cst.Attribute, updated: cst.Attribute) -> cst.BaseExpression:
        if not self.imported_modules:
            return updated
        full = get_full_name_for_node(original)
        if not full:
            return updated
        for module in sorted(self.imported_modules, key=len, reverse=True):
            if full == module or full.startswith(module + "."):
                new = self.m.module(module) + full[len(module):]
                if new != full:
                    self.changed = True
                    return _attr_from_dotted(new)
        return updated

    # --- stringové literály -------------------------------------------------------
    def leave_SimpleString(self, original: cst.SimpleString, updated: cst.SimpleString) -> cst.SimpleString:
        new_value = self.m.text(updated.value)
        if new_value != updated.value:
            self.changed = True
            return updated.with_changes(value=new_value)
        return updated

    def leave_FormattedStringText(
        self, original: cst.FormattedStringText, updated: cst.FormattedStringText
    ) -> cst.FormattedStringText:
        new_value = self.m.text(updated.value)
        if new_value != updated.value:
            self.changed = True
            return updated.with_changes(value=new_value)
        return updated


class _CommentRewriter(cst.CSTTransformer):
    def __init__(self, mapping: Mapping) -> None:
        self.m = mapping

    def leave_Comment(self, original: cst.Comment, updated: cst.Comment) -> cst.Comment:
        new_value = self.m.text(updated.value)
        return updated.with_changes(value=new_value) if new_value != updated.value else updated


def rewrite_python(path: Path, mapping: Mapping) -> bool:
    source = path.read_text(encoding="utf-8")
    module = cst.parse_module(source)
    # dva průchody: nejdřív importy (naplní imported_modules), pak výrazy
    rewriter = Rewriter(mapping)
    first = module.visit(rewriter)
    if rewriter.imported_modules:
        second_rewriter = Rewriter(mapping)
        second_rewriter.imported_modules = set(rewriter.imported_modules)
        # druhý průchod s už přepsanými importy: přepíše jen výrazy
        result = module.visit(second_rewriter)
        changed = second_rewriter.changed
    else:
        result, changed = first, rewriter.changed
    result = result.visit(_CommentRewriter(mapping))
    changed = changed or result.code != source
    if changed and result.code != source:
        path.write_bytes(result.code.encode("utf-8"))
        return True
    return False


def rewrite_text(path: Path, mapping: Mapping) -> bool:
    source = path.read_text(encoding="utf-8")
    new = mapping.text(source)
    if new != source:
        path.write_bytes(new.encode("utf-8"))
        return True
    return False


def iter_python(paths: list[str]):
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix == ".py":
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*.py")):
                if any(part in {".venv", "__pycache__", "node_modules", ".tmp_test_runtime"} for part in f.parts):
                    continue
                yield f


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", required=True)
    parser.add_argument("--text", nargs="*", default=[])
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    mapping = Mapping(json.loads(Path(args.map).read_text(encoding="utf-8")))
    changed = [str(f) for f in iter_python(args.paths) if rewrite_python(f, mapping)]
    changed += [t for t in args.text if Path(t).is_file() and rewrite_text(Path(t), mapping)]
    for f in changed:
        print("rewrote", f)
    print(f"{len(changed)} files changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
