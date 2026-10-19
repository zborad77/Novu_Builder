#!/usr/bin/env python3
"""Porovná dva záznamy pluginu tests/architecture/mock_audit.py (baseline × aktuální).

Selže, pokud některý mock, který byl v baseline v daném testu zavolán, už zavolán
není (patch po přesunu kódu míří jinam), nebo pokud test přišel o patche.
Cíle se porovnávají po aplikaci mapy přesunů (module_map.json), ale porovnání
účinnosti stojí na názvu atributu a pořadí patche v testu – to se přesunem nemění.

    python tools/refactor/compare_mock_audit.py baseline.json current.json
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def _group(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["test"]].append(record)
    return grouped


def compare(baseline: list[dict], current: list[dict]) -> list[str]:
    problems: list[str] = []
    base, cur = _group(baseline), _group(current)
    for test, base_records in sorted(base.items()):
        cur_records = cur.get(test)
        if cur_records is None:
            problems.append(f"MISSING TEST  {test}")
            continue
        # Klíč: (atribut, druh) + pořadí výskytu v testu.
        def keyed(records: list[dict]) -> dict[tuple[str, str, int], dict]:
            seen: dict[tuple[str, str], int] = defaultdict(int)
            out = {}
            for r in records:
                k = (r["attribute"], r["kind"])
                out[(*k, seen[k])] = r
                seen[k] += 1
            return out

        bk, ck = keyed(base_records), keyed(cur_records)
        for key, b in bk.items():
            c = ck.get(key)
            if c is None:
                problems.append(f"LOST PATCH    {test}  {b['target']}.{b['attribute']}")
                continue
            if b.get("tracked") and b.get("called") and not c.get("called"):
                problems.append(
                    f"NOT CALLED    {test}  {b['target']}.{b['attribute']} -> {c['target']}.{c['attribute']}"
                )
    return problems


def main() -> int:
    baseline = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    current = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    problems = compare(baseline, current)
    tracked = sum(1 for r in baseline if r.get("tracked"))
    called = sum(1 for r in baseline if r.get("called"))
    print(f"baseline: {len(baseline)} patches, {tracked} tracked mocks, {called} called")
    print(f"current:  {len(current)} patches, {sum(1 for r in current if r.get('called'))} called")
    for line in problems:
        print(line)
    print("OK – žádný mock neztratil účinnost" if not problems else f"FAIL – {len(problems)} problémů")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
