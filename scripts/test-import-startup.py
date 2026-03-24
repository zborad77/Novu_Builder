"""
Backend import / startup regression check.

Verifies that key backend modules can be imported without errors,
without starting the server or writing to the database.

Modules checked (in dependency order):
  1. app.core.config        — settings / env parsing
  2. app.core.logging       — logging configuration
  3. app.db.base            — SQLAlchemy declarative Base
  4. app.db.session         — engine + session factory
  5. app.models             — all domain models (ORM)
  6. app.api.router         — all route modules + their services,
                              repositories and schemas (transitive)

Usage:
    python scripts/test-import-startup.py
"""

import sys
import os
from pathlib import Path

# Allow running from repo root without modifying PYTHONPATH externally.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "python-backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

CHECKS = [
    ("app.core.config",   "settings / env parsing"),
    ("app.core.logging",  "logging configuration"),
    ("app.db.base",       "SQLAlchemy declarative Base"),
    ("app.db.session",    "engine + session factory"),
    ("app.models",        "all domain models"),
    ("app.api.router",    "all routes, services, repositories, schemas"),
]


def main() -> None:
    print(f"Backend root: {BACKEND_ROOT}\n")

    results: list[tuple[str, bool, str]] = []

    for module, description in CHECKS:
        try:
            __import__(module)
            print(f"  OK    {module}  ({description})")
            results.append((module, True, ""))
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            print(f"  FAIL  {module}  — {msg}")
            results.append((module, False, msg))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
