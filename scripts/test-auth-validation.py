"""
Auth and validation contract smoke test.

Checks:
  401 / 403 — protected endpoints reject requests without a token
  422       — public endpoints reject structurally invalid input

Rules:
  - no login, no token, no DB writes
  - only public POST endpoints with invalid (but structurally harmless) bodies
  - 401/403 tested only on endpoints with known auth dependency

Usage:
    python scripts/test-auth-validation.py
    python scripts/test-auth-validation.py --url http://localhost:8000
"""

import sys
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8000"
TIMEOUT = 5


def _request(method: str, url: str, body: bytes | None = None) -> int | None:
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        print(f"  FAIL  [{method} {url}]  connection error — {exc.reason}")
        return None
    except Exception as exc:
        print(f"  FAIL  [{method} {url}]  unexpected error — {exc}")
        return None


def check(label: str, method: str, url: str, expected: int, body: bytes | None = None) -> bool:
    actual = _request(method, url, body)
    if actual is None:
        return False
    if actual == expected:
        print(f"  OK    {label}  ({actual})")
        return True
    print(f"  FAIL  {label}  expected {expected}, got {actual}")
    return False


def check_auth(label: str, method: str, url: str, body: bytes | None = None) -> bool:
    """Accept 401 or 403 — both are valid 'not authorized' responses."""
    actual = _request(method, url, body)
    if actual is None:
        return False
    if actual in (401, 403):
        print(f"  OK    {label}  ({actual})")
        return True
    print(f"  FAIL  {label}  expected 401 or 403, got {actual}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Auth and validation contract smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL (default: %(default)s)")
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/api/v1"

    empty = json.dumps({}).encode()
    login_no_password = json.dumps({"email": "smoke@test.invalid"}).encode()
    # Valid body structure — body validation passes, auth dependency runs → 401/403
    change_password_valid_body = json.dumps(
        {"currentPassword": "smoke", "newPassword": "smoke"}
    ).encode()

    print(f"Auth & validation contracts: {base}\n")
    print("-- 401 / 403  (no token) --")

    results = [
        check_auth(
            "GET /auth/me requires token",
            "GET", f"{base}/auth/me",
        ),
        check_auth(
            "POST /auth/change-password requires token (valid body, no token)",
            "POST", f"{base}/auth/change-password", body=change_password_valid_body,
        ),

        *([print("") or True][0:0]),  # blank line separator (no-op trick)
    ]

    print("\n-- 422  (invalid input, public endpoints) --")

    results += [
        check(
            "POST /auth/login with empty body returns 422",
            "POST", f"{base}/auth/login", 422, body=empty,
        ),
        check(
            "POST /auth/login missing password returns 422",
            "POST", f"{base}/auth/login", 422, body=login_no_password,
        ),
        check(
            "POST /auth/refresh with empty body returns 422",
            "POST", f"{base}/auth/refresh", 422, body=empty,
        ),
        check(
            "POST /auth/logout with empty body returns 422",
            "POST", f"{base}/auth/logout", 422, body=empty,
        ),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
