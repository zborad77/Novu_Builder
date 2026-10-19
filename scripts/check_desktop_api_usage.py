#!/usr/bin/env python3
"""Kontrakt desktop ↔ API: každá cesta v síťové vrstvě Qt klienta musí existovat v OpenAPI.

Desktop skládá URL jako `m_baseUrl + "/cases/" + id + "/proposal-draft"`, kde
`m_baseUrl` už končí `/api/v1`. Skript vezme všechny řetězcové literály
začínající `/` ze src/desktop/src/network/*.cpp a ověří, že každý je částí
některé šablony cesty v src/contracts/openapi/openapi.json (bez prefixu /api/v1).
Zachytí např. zdvojený prefix `/api/v1/api/v1/admin/...` (REFACTOR_FINDINGS N4)
nebo volání endpointu, který backend nemá.

    python scripts/check_desktop_api_usage.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "src" / "desktop" / "src" / "network"
OPENAPI = ROOT / "src" / "contracts" / "openapi" / "openapi.json"
API_PREFIX = "/api/v1"
LITERAL = re.compile(r'"(/[^"\s]*)"')


def api_paths() -> list[str]:
    paths = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    return [p[len(API_PREFIX):] if p.startswith(API_PREFIX) else p for p in paths]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    templates = api_paths()
    problems: list[str] = []
    checked = 0
    for source in sorted(NETWORK.glob("*.cpp")):
        for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            for literal in LITERAL.findall(line):
                fragment = literal.split("?", 1)[0].rstrip("/")
                if not fragment:
                    continue
                checked += 1
                if not any(fragment in template for template in templates):
                    problems.append(f"{source.relative_to(ROOT).as_posix()}:{lineno}: {literal!r} není v OpenAPI kontraktu")
    for problem in problems:
        print(problem)
    print(f"{checked} cest z desktopu ověřeno proti {len(templates)} šablonám API"
          + ("" if not problems else f" – {len(problems)} chyb"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
