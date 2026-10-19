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


def _fallback_root(backend_root: Path) -> Path:
    """Kořen bez markeru: v rozložení repozitáře `<kořen>/src/backend`, jinak rodič backendu.

    Docker image má backend v `/app` (bez zbytku repozitáře) – kořenem je pak `/`,
    stejně jako před přesunem do src/ (výchozí dev úložiště `/storage`).
    """
    if backend_root.parent.name == "src" and len(backend_root.parents) > 1:
        return backend_root.parents[1]
    return backend_root.parent


@lru_cache(maxsize=1)
def repo_root() -> Path:
    for candidate in (BACKEND_ROOT, *BACKEND_ROOT.parents):
        if (candidate / REPO_ROOT_MARKER).is_file():
            return candidate
    return _fallback_root(BACKEND_ROOT)
