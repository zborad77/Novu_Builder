"""
Redis connectivity check — TCP socket only, no PING command.

Reads REDIS_URL from environment.
If REDIS_URL is not set → SKIP (exit code 0).

Usage:
    REDIS_URL=redis://localhost:6379/0 python scripts/test-redis-connection.py
    python scripts/test-redis-connection.py  (uses REDIS_URL from env)
"""

import os
import sys
import socket
import urllib.parse

REDIS_URL = os.environ.get("REDIS_URL", "")


def fail(reason: str) -> None:
    print(f"FAIL: {reason}")
    sys.exit(1)


def main() -> None:
    if not REDIS_URL:
        print("SKIP: REDIS_URL is not set")
        sys.exit(0)

    parsed = urllib.parse.urlparse(REDIS_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    print(f"Connecting to Redis {host}:{port} ...")

    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
    except socket.timeout:
        fail(f"timed out connecting to {host}:{port}")
    except OSError as exc:
        fail(f"connection error — {exc}")

    print("OK")


if __name__ == "__main__":
    main()
