"""
Backend startup self-check.

Checks:
  1. GET /api/v1/health returns HTTP 200
  2. Response body is valid JSON
  3. Response arrives within TIMEOUT seconds

Usage:
    python scripts/test-backend-startup.py
    python scripts/test-backend-startup.py --url http://localhost:8000
    python scripts/test-backend-startup.py --timeout 3
"""

import sys
import json
import argparse
import socket
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000"
HEALTH_PATH = "/api/v1/health"
DEFAULT_TIMEOUT = 5


def fail(reason: str) -> None:
    print(f"FAIL: {reason}")
    sys.exit(1)


def check_startup(base_url: str, timeout: int) -> None:
    url = base_url.rstrip("/") + HEALTH_PATH
    print(f"GET {url}  (timeout={timeout}s)")

    # --- HTTP request ---
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        fail(f"HTTP {exc.code}")
    except socket.timeout:
        fail(f"timed out after {timeout}s")
    except urllib.error.URLError as exc:
        fail(f"connection error — {exc.reason}")
    except Exception as exc:
        fail(f"unexpected error — {exc}")

    # --- status check ---
    if status != 200:
        fail(f"expected HTTP 200, got {status}")

    # --- JSON check ---
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"response is not valid JSON — {exc}")

    print("OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backend startup self-check")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL (default: %(default)s)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout in seconds (default: %(default)s)")
    args = parser.parse_args()
    check_startup(args.url, args.timeout)
