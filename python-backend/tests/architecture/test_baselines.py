"""Modulární refaktor: API, routy, middlewary, bezpečnostní povrch, ORM metadata a
migrace musí zůstat shodné s baseline (scripts/export_contracts.py) a stringové
cíle mocků v testech musí mířit na místa, kde se jméno skutečně používá."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Export běží v čistém procesu: conftest nastavuje testovací rate limity aj.,
# které by změnily bezpečnostní povrch. Předáváme jen systémové proměnné.
_SYSTEM_ENV = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL",
}


def _clean_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in _SYSTEM_ENV}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_contracts_and_architecture_baselines_unchanged():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.export_contracts", "--check"],
        cwd=BACKEND_ROOT,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-4000:]


def test_string_mock_targets_point_at_used_names():
    result = subprocess.run(
        [sys.executable, "tools/refactor/check_patch_targets.py", "--max-ineffective", "0"],
        cwd=BACKEND_ROOT,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
