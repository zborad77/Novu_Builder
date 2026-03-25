"""
Business flow smoke test — critical path: create case → trigger analysis → verify result.

Steps:
  1. Login with dev-seed credentials           → 200 + accessToken
  2. Create a smoke-test case                  → 201 + id
  3. Read the case back                        → 200 + id matches
  4. Trigger analysis (expects mock provider)  → 202 + jobId
  5. Poll until job completed / failed         → completed within 30 s
  6. Verify result has required output fields  → objectType, estimatedAreaSqm, materials, workflowSteps
  7. Archive case (cleanup)                    → 200

Requires:
  - Backend running with dev seed (SEED_ON_STARTUP=true / APP_ENV=development)
  - AI_ANALYSIS_PROVIDER=mock  (no external API calls)
  - Default credentials: demo@novu.local / demo1234

Usage:
    python scripts/test-business-flow.py
    python scripts/test-business-flow.py --url http://localhost:8000
    python scripts/test-business-flow.py --email demo@novu.local --password demo1234
    python scripts/test-business-flow.py --skip-cleanup
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "http://localhost:8000"
TIMEOUT = 10
POLL_INTERVAL = 1          # seconds between job status checks
POLL_MAX_WAIT = 30         # total seconds before giving up


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request(
    method: str,
    url: str,
    body: bytes | None = None,
    token: str | None = None,
) -> tuple[int, dict | None]:
    """Return (status_code, parsed_json_or_None)."""
    headers: dict[str, str] = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, None
    except urllib.error.URLError as exc:
        print(f"  FAIL  [{method} {url}]  connection error — {exc.reason}")
        return -1, None
    except Exception as exc:
        print(f"  FAIL  [{method} {url}]  unexpected error — {exc}")
        return -1, None


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    suffix = f"  ({detail})" if detail else ""
    print(f"  OK    {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    suffix = f"  — {detail}" if detail else ""
    print(f"  FAIL  {label}{suffix}")


def assert_status(label: str, actual: int, expected: int) -> bool:
    if actual == expected:
        ok(label, str(actual))
        return True
    fail(label, f"expected {expected}, got {actual}")
    return False


def assert_field(label: str, data: dict | None, field: str) -> bool:
    if data and data.get(field) is not None:
        ok(label, f"{field}={data[field]!r}")
        return True
    fail(label, f"field '{field}' missing or null in response")
    return False


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Business flow smoke test")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--email", default="demo@novu.local")
    parser.add_argument("--password", default="demo1234")
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Leave the test case in the database (useful for manual inspection)",
    )
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/api/v1"

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    case_title = f"[smoke-test] {ts}"
    token: str | None = None
    case_id: str | None = None

    print(f"Business flow: {base}")
    print(f"User:          {args.email}")
    print(f"Case title:    {case_title}\n")

    # ------------------------------------------------------------------
    # Step 1 — Login
    # ------------------------------------------------------------------
    print("-- Step 1: Login --")
    status, body = _request(
        "POST",
        f"{base}/auth/login",
        json.dumps({"email": args.email, "password": args.password}).encode(),
    )
    if not assert_status("POST /auth/login", status, 200):
        _abort("Login failed — is the backend running with dev seed?")
        return
    if not assert_field("accessToken present", body, "accessToken"):
        _abort("Login response malformed.")
        return
    token = body["accessToken"]  # type: ignore[index]

    # ------------------------------------------------------------------
    # Step 2 — Create case
    # ------------------------------------------------------------------
    print("\n-- Step 2: Create case --")
    status, body = _request(
        "POST",
        f"{base}/cases",
        json.dumps({
            "title": case_title,
            "description": "Automated smoke-test case — safe to archive.",
            "propertyType": "house",
            "repairScope": "full_reconstruction",
        }).encode(),
        token=token,
    )
    if not assert_status("POST /cases", status, 201):
        _abort("Could not create test case.")
        return
    if not assert_field("case id returned", body, "id"):
        _abort("Create case response malformed.")
        return
    case_id = body["id"]  # type: ignore[index]

    # ------------------------------------------------------------------
    # Step 3 — Read case back
    # ------------------------------------------------------------------
    print("\n-- Step 3: Read case --")
    status, body = _request("GET", f"{base}/cases/{case_id}", token=token)
    assert_status("GET /cases/{id}", status, 200)
    if body and body.get("id") == case_id:
        ok("case id matches")
    else:
        fail("case id matches", f"got {body.get('id') if body else None!r}")

    # ------------------------------------------------------------------
    # Step 4 — Trigger analysis
    # ------------------------------------------------------------------
    print("\n-- Step 4: Trigger analysis --")
    status, body = _request(
        "POST",
        f"{base}/cases/{case_id}/analysis-jobs",
        b"",
        token=token,
    )
    if not assert_status("POST /cases/{id}/analysis-jobs", status, 202):
        _abort("Could not trigger analysis.", case_id=case_id, base=base, token=token, skip=args.skip_cleanup)
        return
    if not assert_field("jobId returned", body, "jobId"):
        _abort("Trigger response malformed.", case_id=case_id, base=base, token=token, skip=args.skip_cleanup)
        return

    job_id = body["jobId"]  # type: ignore[index]
    provider = body.get("provider", "?")  # type: ignore[index]
    ok("provider", provider)

    if provider not in ("mock", "?"):
        print(f"\n  WARN  provider={provider!r} — this test is designed for mock provider.")
        print("        Real AI calls may be slow or fail if API keys are not set.")

    # ------------------------------------------------------------------
    # Step 5 — Poll job to completion
    # ------------------------------------------------------------------
    print(f"\n-- Step 5: Poll job {job_id} (max {POLL_MAX_WAIT}s) --")
    deadline = time.monotonic() + POLL_MAX_WAIT
    job_status = "queued"
    elapsed = 0.0

    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        status, job = _request("GET", f"{base}/analysis-jobs/{job_id}", token=token)
        if status != 200 or not job:
            fail(f"poll attempt at {elapsed:.0f}s", f"status={status}")
            break
        job_status = job.get("status", "unknown")
        print(f"  ...   {elapsed:.0f}s  status={job_status}")
        if job_status in ("completed", "failed", "cancelled"):
            break

    if job_status == "completed":
        ok("job completed", f"in {elapsed:.0f}s")
    else:
        fail("job completed", f"final status={job_status!r} after {elapsed:.0f}s")

    # ------------------------------------------------------------------
    # Step 6 — Verify result fields
    # ------------------------------------------------------------------
    print("\n-- Step 6: Verify analysis result fields --")
    if job_status == "completed":
        result_url = f"{base}/cases/{case_id}"
        status, detail = _request("GET", result_url, token=token)
        if status == 200 and detail:
            analysis = detail.get("latestAnalysis") or {}
            for field in ("objectType", "estimatedAreaSqm", "materials", "workflowSteps"):
                assert_field(f"result.{field}", analysis, field)
        else:
            fail("GET case detail for result", f"status={status}")
    else:
        print("  SKIP  (job did not complete)")

    # ------------------------------------------------------------------
    # Step 7 — Cleanup: archive case
    # ------------------------------------------------------------------
    _cleanup(case_id, base, token, args.skip_cleanup)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = _passed + _failed
    print(f"\n{_passed}/{total} passed")
    if _failed:
        sys.exit(1)


def _abort(reason: str, case_id: str | None = None, base: str = "", token: str | None = None, skip: bool = False) -> None:
    global _failed
    _failed += 1
    print(f"\n  ABORT {reason}")
    if case_id:
        _cleanup(case_id, base, token, skip)


def _cleanup(case_id: str | None, base: str, token: str | None, skip: bool) -> None:
    if not case_id:
        return
    print("\n-- Step 7: Cleanup (archive case) --")
    if skip:
        print(f"  SKIP  --skip-cleanup set. Case {case_id!r} left in database.")
        return
    status, _ = _request(
        "POST",
        f"{base}/cases/{case_id}/archive",
        b"",
        token=token,
    )
    if status == 200:
        ok(f"case {case_id!r} archived")
    else:
        print(f"  WARN  archive returned {status} — case may remain in database")


if __name__ == "__main__":
    main()
