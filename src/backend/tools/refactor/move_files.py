#!/usr/bin/env python3
"""git mv souborů podle mapy etapy (jen celé moduly / balíčky) + vytvoření __init__.py.

    python tools/refactor/move_files.py tools/refactor/stages/b2_platform.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def path_of(module: str) -> Path:
    base = BACKEND / Path(*module.split("."))
    return base if base.is_dir() else base.with_suffix(".py")


def ensure_package(directory: Path) -> None:
    app_root = BACKEND / "app"
    current = directory
    while current != app_root and app_root in current.parents:
        init = current / "__init__.py"
        if not init.exists():
            current.mkdir(parents=True, exist_ok=True)
            init.write_text("", encoding="utf-8")
            subprocess.run(["git", "add", str(init)], cwd=BACKEND, check=True)
        current = current.parent


def main() -> int:
    mapping = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["modules"]
    for old, new in mapping.items():
        src = path_of(old)
        if not src.exists():
            print(f"skip (missing) {old}")
            continue
        new_base = BACKEND / Path(*new.split("."))
        dst = new_base if src.is_dir() else new_base.with_suffix(".py")
        ensure_package(dst.parent)
        subprocess.run(["git", "mv", str(src), str(dst)], cwd=BACKEND, check=True)
        print(f"mv {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
