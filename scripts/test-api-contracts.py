"""
Read-only smoke test for basic HTTP API contracts.

Contracts tested:
  1. GET  /api/v1/            → 200  (public root)
  2. GET  /api/v1/health      → 200  (public health)
  3. GET  /api/v1/cases       → 401  (protected, no token)
  4. GET  /api/v1/admin/users → 401  (protected admin, no token)
  5. GET  /api/v1/analysis-jobs/smoke-test-nonexistent → 401  (protected, no token)
  6. GET  /api/v1/__no_such_endpoint__ → 404  (unknown route)
  7. DELETE /api/v1/health    → 405  (method not allowed on GET-only route)
  8. GET  /api/v1/auth/login  → 405  (login is POST-only)

No writes, no auth, no side effects.

Usage:
    python scripts/test-api-contracts.py
    python scripts/test-api-contracts.py --url http://localhost:8000
"""

import sys
import argparse
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000"
TIMEOUT = 5


def check(label: str, method: str, url: str, expected_status: int) -> bool:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            actual = resp.status
    except urllib.error.HTTPError as exc:
        actual = exc.code
    except urllib.error.URLError as exc:
        print(f"  FAIL  [{method} {url}]  connection error — {exc.reason}")
        return False
    except Exception as exc:
        print(f"  FAIL  [{method} {url}]  unexpected error — {exc}")
        return False

    if actual == expected_status:
        print(f"  OK    {label}  ({actual})")
        return True
    else:
        print(f"  FAIL  {label}  expected {expected_status}, got {actual}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="API HTTP contract smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL (default: %(default)s)")
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/api/v1"

    print(f"API contracts: {base}\n")

    results = [
        check("public root returns 200",                   "GET",    f"{base}/",                                200),
        check("public health returns 200",                 "GET",    f"{base}/health",                          200),
        check("protected /cases returns 401 without token","GET",    f"{base}/cases",                           401),
        check("protected /admin/users returns 401",        "GET",    f"{base}/admin/users",                     401),
        check("protected /analysis-jobs/:id returns 401",  "GET",    f"{base}/analysis-jobs/smoke-nonexistent", 401),
        check("unknown route returns 404",                 "GET",    f"{base}/__no_such_endpoint__",            404),
        check("DELETE /health returns 405",                "DELETE", f"{base}/health",                          405),
        check("GET /auth/login returns 405",               "GET",    f"{base}/auth/login",                      405),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
