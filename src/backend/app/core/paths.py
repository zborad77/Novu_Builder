"""Kořenové cesty repozitáře nezávislé na hloubce adresářů.

Backend leží v `src/backend/`; kořen repozitáře se hledá podle markeru
`.novu-repo-root` (je součástí release balíčku), takže přesun adresářů
nevyžaduje přepočítávat `parents[N]` na desítkách míst.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT_MARKER = ".novu-repo-root"


@lru_cache(maxsize=1)
def repo_root() -> Path:
    for candidate in (BACKEND_ROOT, *BACKEND_ROOT.parents):
        if (candidate / REPO_ROOT_MARKER).is_file():
            return candidate
    # Release bez markeru: backend je vždy src/backend v kořeni repozitáře.
    return BACKEND_ROOT.parents[1]
