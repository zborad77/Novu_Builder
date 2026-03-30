from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_deploy import main


def _translate_legacy_args(argv: list[str]) -> list[str]:
    translated: list[str] = []
    remaining = list(argv)

    if remaining and not remaining[0].startswith("-"):
        translated.extend(["--base-url", remaining.pop(0)])
    if remaining and not remaining[0].startswith("-"):
        translated.extend(["--auth-email", remaining.pop(0)])
    if remaining and not remaining[0].startswith("-"):
        translated.extend(["--auth-password", remaining.pop(0)])

    translated.extend(remaining)
    return translated


if __name__ == "__main__":
    sys.exit(main(_translate_legacy_args(sys.argv[1:])))
