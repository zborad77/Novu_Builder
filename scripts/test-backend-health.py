"""
Minimal smoke test — backend health check.
Usage:
    python scripts/test-backend-health.py
    python scripts/test-backend-health.py --url http://localhost:8000
"""

import sys
import argparse
import socket
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000"
HEALTH_PATH = "/api/v1/health"
TIMEOUT = 5


def check_health(base_url: str) -> None:
    url = base_url.rstrip("/") + HEALTH_PATH
    print(f"GET {url}")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            status = response.status
            body = response.read().decode()
    except urllib.error.HTTPError as exc:
        print(f"FAIL: HTTP {exc.code}")
        sys.exit(1)
    except socket.timeout:
        print(f"FAIL: timed out after {TIMEOUT}s")
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"FAIL: connection error — {exc.reason}")
        sys.exit(1)
    except Exception as exc:
        print(f"FAIL: unexpected error — {exc}")
        sys.exit(1)

    if status != 200:
        print(f"FAIL: expected 200, got {status}")
        sys.exit(1)

    print("OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backend health smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL (default: %(default)s)")
    args = parser.parse_args()
    check_health(args.url)
