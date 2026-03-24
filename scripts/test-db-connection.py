"""
DB connectivity check — TCP socket only, no SQL.

Reads DATABASE_URL from environment.
Supports: postgresql://, sqlite:///

Usage:
    DATABASE_URL=postgresql://user:pass@localhost:5432/db python scripts/test-db-connection.py
    python scripts/test-db-connection.py  (uses DATABASE_URL from env)
"""

import os
import sys
import socket
import urllib.parse

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def fail(reason: str) -> None:
    print(f"FAIL: {reason}")
    sys.exit(1)


def check_postgres(url: str) -> None:
    # strip driver prefix (e.g. postgresql+asyncpg:// -> postgresql://)
    normalized = url.split("+")[0] + "://" + url.split("://", 1)[1]
    parsed = urllib.parse.urlparse(normalized)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    print(f"Connecting to PostgreSQL {host}:{port} ...")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
    except socket.timeout:
        fail(f"timed out connecting to {host}:{port}")
    except OSError as exc:
        fail(f"connection error — {exc}")
    print("OK")


def check_sqlite(url: str) -> None:
    # sqlite:///./path  or  sqlite+aiosqlite:///./path
    path_part = url.split("///", 1)[-1]
    # resolve relative path from cwd
    abs_path = os.path.abspath(path_part)
    directory = os.path.dirname(abs_path) or "."
    print(f"Checking SQLite path: {abs_path}")
    if not os.path.isdir(directory):
        fail(f"directory does not exist: {directory}")
    print("OK")


def main() -> None:
    if not DATABASE_URL:
        fail("DATABASE_URL is not set")

    url_lower = DATABASE_URL.lower()
    if url_lower.startswith("postgresql") or url_lower.startswith("postgres"):
        check_postgres(DATABASE_URL)
    elif url_lower.startswith("sqlite"):
        check_sqlite(DATABASE_URL)
    else:
        fail(f"unsupported database scheme in DATABASE_URL: {DATABASE_URL.split(':')[0]}")


if __name__ == "__main__":
    main()
