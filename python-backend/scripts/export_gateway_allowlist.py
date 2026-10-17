#!/usr/bin/env python3
"""Generate the Public Edge gateway allowlist from app/core/exposure.py (F3.5).

The gateway (F4) forwards only these (method, route template) pairs to the core's
gateway zone; everything else is answered 404 at the edge. The file is committed
and CI (tests/test_gateway_allowlist.py) fails when it drifts from EXPOSURE.

    python -m scripts.export_gateway_allowlist            # rewrite the file
    python -m scripts.export_gateway_allowlist --check    # exit 1 if stale
"""
import argparse
import json
import sys
from pathlib import Path

from app.core.exposure import EXPOSURE, ZONE_GATEWAY

TARGET = Path(__file__).resolve().parents[2] / "docs" / "security" / "gateway-allowlist.json"


def gateway_routes() -> list[dict[str, str]]:
    return [
        {"method": method, "path": path}
        for method, path in sorted(
            (key for key, zones in EXPOSURE.items() if ZONE_GATEWAY in zones),
            key=lambda key: (key[1], key[0]),
        )
    ]


def render() -> str:
    routes = gateway_routes()
    document = {
        "generatedFrom": "python-backend/app/core/exposure.py",
        "zone": ZONE_GATEWAY,
        "count": len(routes),
        "routes": routes,
    }
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    args = parser.parse_args()
    content = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print(f"{TARGET} is stale; run python -m scripts.export_gateway_allowlist", file=sys.stderr)
            return 1
        return 0
    TARGET.write_bytes(content.encode("utf-8"))
    print(f"wrote {TARGET} ({len(gateway_routes())} routes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
