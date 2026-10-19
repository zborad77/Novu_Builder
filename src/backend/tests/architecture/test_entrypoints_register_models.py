"""Každý vstupní bod musí zavolat app.composition.wiring.init_modules().

Tím registruje všechny ORM modely a propojí porty mezi moduly.

Relace mezi modely různých modulů jsou deklarované stringem; pokud vstupní bod
naimportuje jen část modelů, selže konfigurace mapperů až za běhu (zjištěno při
refaktoru u scripts/validate_restored_media.py). Test spouští každý vstupní bod
v čistém interpretu, kde ho nezakryjí importy ostatních testů.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

ENTRYPOINTS = [
    "app.main",
    "app.worker.runner",
    "app.worker.offer_runner",
    "scripts.check_storage_consistency",
    "scripts.create_pilot_admin",
    "scripts.export_s3_recovery_manifest",
    "scripts.reapply_photo_purges",
    "scripts.restore_s3_media",
    "scripts.validate_restored_media",
]


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_entrypoint_configures_all_mappers(module, tmp_path):
    env = {
        **{k: v for k, v in os.environ.items() if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE"}},
        "NOVU_IGNORE_ENV_FILES": "1",
        "APP_ENV": "development",
        "JWT_SECRET": "entrypoint-check-not-a-secret-0123456789",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}",
        "AI_ANALYSIS_PROVIDER": "mock",
        "PYTHONIOENCODING": "utf-8",
    }
    code = f"import {module}\nfrom sqlalchemy.orm import configure_mappers\nconfigure_mappers()\n"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr[-3000:]
