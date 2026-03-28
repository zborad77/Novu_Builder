#!/usr/bin/env python3
"""Post-deploy smoke check for Novu Builder Python backend.

Verifies that a live (or staging) deployment is healthy by hitting real
HTTP endpoints and asserting expected status codes and response shapes.
Does NOT modify state — all requests are read-only except the login flow
(which creates a session token in-memory only).

Usage:
    python scripts/smoke_check_live.py [BASE_URL] [EMAIL] [PASSWORD]

Defaults:
    BASE_URL  = http://localhost:8000
    EMAIL     = manager_a@test.local   (test tenant; override for production)
    PASSWORD  = TestPassA1!

Exit code: 0 if all checks pass, 1 if any check fails.

Environment variables (override CLI args):
    SMOKE_BASE_URL
    SMOKE_EMAIL
    SMOKE_PASSWORD
    SMOKE_METRICS_TOKEN   (if METRICS_AUTH_ENABLED=true)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("SMOKE_BASE_URL") or (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
EMAIL = os.environ.get("SMOKE_EMAIL") or (sys.argv[2] if len(sys.argv) > 2 else "manager_a@test.local")
PASSWORD = os.environ.get("SMOKE_PASSWORD") or (sys.argv[3] if len(sys.argv) > 3 else "TestPassA1!")
METRICS_TOKEN = os.environ.get("SMOKE_METRICS_TOKEN", "")

BASE_URL = BASE_URL.rstrip("/")

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: int = 10,
) -> tuple[int, dict | str]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def get(path: str, *, token: str = "", extra_headers: dict | None = None) -> tuple[int, Any]:
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra_headers:
        h.update(extra_headers)
    return _request("GET", path, headers=h)


def post(path: str, body: dict | None = None, *, token: str = "") -> tuple[int, Any]:
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return _request("POST", path, body=body, headers=h)


# ── Check runner ──────────────────────────────────────────────────────────────

_passed = 0
_failed = 0
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _passed, _failed
    if condition:
        _passed += 1
        _results.append((name, True, detail))
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        _results.append((name, False, detail))
        print(f"  [FAIL] {name}  →  {detail}")
    return condition


# ── Smoke checks ──────────────────────────────────────────────────────────────

def run_checks() -> None:
    print(f"\nNovu Builder smoke check — {BASE_URL}\n")

    # 1. Liveness
    print("── Liveness ─────────────────────────────────────────────────────────")
    status, body = get("/api/v1/alive")
    check("GET /alive returns 200", status == 200, f"status={status}")
    check("/alive body has status=alive", isinstance(body, dict) and body.get("status") == "alive", str(body))

    # 2. Public health
    print("── Public health ────────────────────────────────────────────────────")
    status, body = get("/api/v1/health")
    check("GET /health returns 200", status == 200, f"status={status}")
    check("/health has status field", isinstance(body, dict) and "status" in body, str(body))
    check("/health status is ok or degraded", body.get("status") in ("ok", "degraded") if isinstance(body, dict) else False, str(body))

    # 3. Root endpoint
    print("── Root ─────────────────────────────────────────────────────────────")
    status, body = get("/api/v1/")
    check("GET / returns 200", status == 200, f"status={status}")

    # 4. Auth — login
    print("── Auth login ───────────────────────────────────────────────────────")
    status, body = post("/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    login_ok = check("POST /auth/login returns 200", status == 200, f"status={status}: {body}")
    token = ""
    if login_ok and isinstance(body, dict):
        token = body.get("accessToken", "")
        check("login response has accessToken", bool(token), str(body))
        check("login response has user object", "user" in body, str(body))

    # 5. Auth — /me
    print("── Auth /me ─────────────────────────────────────────────────────────")
    if token:
        status, body = get("/api/v1/auth/me", token=token)
        check("GET /auth/me returns 200 with valid token", status == 200, f"status={status}: {body}")
        check("/auth/me has email field", isinstance(body, dict) and "email" in body, str(body))
    else:
        check("GET /auth/me (skipped — no token)", False, "login failed, skipping auth/me")

    # 6. Auth — reject bad token
    print("── Auth token rejection ─────────────────────────────────────────────")
    status, body = get("/api/v1/auth/me", token="invalid.jwt.token")
    check("GET /auth/me with bad token returns 401", status == 401, f"status={status}")

    # 7. Cases list
    print("── Cases ────────────────────────────────────────────────────────────")
    if token:
        status, body = get("/api/v1/cases", token=token)
        check("GET /cases returns 200", status == 200, f"status={status}: {body}")
        check("/cases returns a list or paginated object", isinstance(body, (list, dict)), str(type(body)))
    else:
        check("GET /cases (skipped — no token)", False, "login failed")

    # 8. Cases list unauthenticated
    status, body = get("/api/v1/cases")
    check("GET /cases without token returns 401", status == 401, f"status={status}")

    # 9. Metrics endpoint
    print("── Metrics ──────────────────────────────────────────────────────────")
    if METRICS_TOKEN:
        status, body = get("/api/v1/metrics", extra_headers={"Authorization": f"Bearer {METRICS_TOKEN}"})
        check("GET /metrics with correct token returns 200", status == 200, f"status={status}")
        status, body = get("/api/v1/metrics")
        check("GET /metrics without token returns 401", status == 401, f"status={status}")
    else:
        # Try without token — if guard is disabled (dev env) expect 200; if enabled expect 401
        status, body = get("/api/v1/metrics")
        check("GET /metrics reachable (200 or 401)", status in (200, 401), f"status={status}")
        if status == 200:
            check("/metrics body is Prometheus text format", "http_requests_total" in (body if isinstance(body, str) else ""), str(body)[:100])

    # 10. Admin endpoint requires superadmin
    print("── Admin guards ─────────────────────────────────────────────────────")
    if token:
        status, body = get("/api/v1/admin/users", token=token)
        # Regular manager should get 403 Forbidden
        check("GET /admin/users with manager token returns 403", status == 403, f"status={status}")

    # 11. 404 for unknown routes
    print("── 404 handling ─────────────────────────────────────────────────────")
    status, body = get("/api/v1/nonexistent_endpoint_xyz")
    check("Unknown endpoint returns 404", status == 404, f"status={status}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = _passed + _failed
    print(f"\n{'─' * 68}")
    print(f"Results: {_passed}/{total} passed", end="")
    if _failed:
        print(f", {_failed} FAILED")
        print("\nFailed checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  • {name}: {detail}")
    else:
        print(" — all checks passed")
    print()


if __name__ == "__main__":
    run_checks()
    sys.exit(0 if _failed == 0 else 1)
