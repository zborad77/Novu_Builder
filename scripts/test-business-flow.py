"""
Critical business flow smoke test.

Tests the full end-to-end lifecycle of a case and analysis job:
  1. Login           — authenticate with test credentials        → 200 + accessToken
  2. Create case     — POST /cases with [FLOW-TEST] title        → 201 + id
  3. Fetch case      — GET /cases/{id} and verify id             → 200 + id matches
  4. Trigger job     — POST /cases/{id}/analysis-jobs            → 202 + jobId
  5. Poll job        — GET /analysis-jobs/{jobId} until terminal → completed / failed
  6. Verify result   — latestAnalysis present on case detail     → not null
  7. Archive case    — POST /cases/{id}/archive (always runs)    → 200

Credentials (required — no hard-coded defaults):
  NOVU_TEST_EMAIL    env var  OR  --email flag
  NOVU_TEST_PASSWORD env var  OR  --password flag

  If credentials are not available the script exits with code 2 (SKIP).

Usage:
    NOVU_TEST_EMAIL=admin@novu.cz NOVU_TEST_PASSWORD=secret python scripts/test-business-flow.py
    python scripts/test-business-flow.py --email demo@novu.local --password demo1234
    python scripts/test-business-flow.py --url http://localhost:8000 --email u@e.com --password p
    python scripts/test-business-flow.py --skip-cleanup   (leave case in DB for inspection)

Exit codes:
  0 — all steps passed
  1 — one or more steps failed
  2 — credentials not provided (treated as SKIP by run-all-checks.py --include-flow)

Notes:
  - Creates only data with title prefix "[FLOW-TEST]" — safe to archive
  - Archive (step 7) runs unconditionally if a case was created (via try/finally)
  - Archive failure is reported as secondary warning, never overwrites main flow result
  - Polling uses time.monotonic() — immune to system clock changes
  - Polling logs status transitions only, not every identical poll
  - Poll timeout: 120 s (enough for real providers; mock completes in < 5 s)
  - Consecutive HTTP errors during polling abort poll after 3 failures
  - Response bodies in diagnostics are truncated to 300 chars
  - Passwords and tokens are never logged
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "http://localhost:8000"
HTTP_TIMEOUT = 10                  # per-request HTTP timeout (seconds)
POLL_INTERVAL = 3                  # seconds between job status polls
POLL_MAX_WAIT = 120                # total seconds to wait for job terminal state
POLL_MAX_CONSECUTIVE_ERRORS = 3   # abort poll after N consecutive HTTP errors
TEST_TITLE_PREFIX = "[FLOW-TEST]"
TERMINAL_STATUSES = {"completed", "failed", "canceled", "cancelled", "error"}
MAX_BODY_LOG = 300                 # truncate response bodies in diagnostics


# ---------------------------------------------------------------------------
# Diagnostics context — populated as flow progresses, used in fail messages
# ---------------------------------------------------------------------------

_ctx: dict = {}   # keys: case_id, job_id, last_job_status


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _request(
    method: str,
    url: str,
    body: bytes | None = None,
    token: str | None = None,
) -> tuple[int, dict | list | None]:
    """Return (http_status, parsed_json_or_None). Never raises."""
    headers: dict[str, str] = {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
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
        print(f"    connection error  [{method} {url}]  — {exc.reason}")
        return 0, None
    except Exception as exc:
        print(f"    unexpected error  [{method} {url}]  — {exc}")
        return 0, None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def _step(n: int, label: str) -> None:
    bar = "─" * max(0, 40 - len(label))
    print(f"\n── Step {n}: {label} {bar}", flush=True)


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


def _diag(label: str, endpoint: str, http_status: int, body: object = None) -> None:
    """Print failure diagnostics. Never logs token, password, or full payloads."""
    print(f"  DIAG  {label}")
    print(f"        endpoint    : {endpoint}")
    print(f"        http_status : {http_status}")
    if body is not None:
        print(f"        response    : {_truncate(body)}")
    if _ctx.get("case_id"):
        print(f"        case_id     : {_ctx['case_id']}")
    if _ctx.get("job_id"):
        print(f"        job_id      : {_ctx['job_id']}")
    if _ctx.get("last_job_status"):
        print(f"        last_status : {_ctx['last_job_status']}")


def _truncate(body: object) -> str:
    raw = json.dumps(body) if not isinstance(body, str) else body
    return raw[:MAX_BODY_LOG] + ("…" if len(raw) > MAX_BODY_LOG else "")


def _safe_body(body: object) -> object:
    """Redact credential fields before passing to diagnostics."""
    REDACT = {"accessToken", "refreshToken", "token", "password", "secret"}
    if not isinstance(body, dict):
        return body
    return {k: ("<redacted>" if k in REDACT else v) for k, v in body.items()}


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

def _poll_job(url: str, token: str | None) -> str:
    """
    Poll job status URL until a terminal status is reached or POLL_MAX_WAIT expires.

    - Uses time.monotonic() — immune to system clock changes.
    - Logs only on status transitions, not on every identical poll.
    - Allows up to POLL_MAX_CONSECUTIVE_ERRORS HTTP errors before aborting.
    - Returns the last known job status string.
    """
    start = time.monotonic()
    deadline = start + POLL_MAX_WAIT
    last_logged_status: str | None = None
    consecutive_errors = 0
    job_status = "unknown"
    poll_n = 0

    while True:
        now = time.monotonic()
        remaining = deadline - now

        if remaining <= 0:
            elapsed = now - start
            fail(
                "poll job timeout",
                f"did not reach terminal status within {POLL_MAX_WAIT}s  "
                f"last_status={job_status!r}  elapsed={elapsed:.1f}s",
            )
            print(
                f"  DIAG  timeout polling {url}\n"
                f"        last_status={job_status!r}  elapsed={elapsed:.1f}s"
            )
            return job_status

        time.sleep(min(POLL_INTERVAL, remaining))
        poll_n += 1
        elapsed = time.monotonic() - start

        http_status, body = _request("GET", url, token=token)

        if http_status != 200 or not isinstance(body, dict):
            consecutive_errors += 1
            print(
                f"  WARN  poll #{poll_n} at {elapsed:.1f}s — HTTP {http_status}  "
                f"(errors: {consecutive_errors}/{POLL_MAX_CONSECUTIVE_ERRORS})",
                flush=True,
            )
            if consecutive_errors >= POLL_MAX_CONSECUTIVE_ERRORS:
                fail(
                    "poll job aborted",
                    f"{consecutive_errors} consecutive HTTP errors  "
                    f"last_status={job_status!r}  url={url}",
                )
                return job_status
            continue

        consecutive_errors = 0
        job_status = body.get("status") or "unknown"

        # Log only on status change — suppress identical-poll noise
        if job_status != last_logged_status:
            arrow = f"{last_logged_status!r} → " if last_logged_status is not None else ""
            print(f"  ...   {elapsed:.1f}s  status: {arrow}{job_status!r}", flush=True)
            last_logged_status = job_status

        if job_status in TERMINAL_STATUSES:
            if job_status == "completed":
                ok("job reached terminal state", f"completed  elapsed={elapsed:.1f}s  polls={poll_n}")
            else:
                fail(
                    "job reached terminal state",
                    f"status={job_status!r}  elapsed={elapsed:.1f}s  polls={poll_n}",
                )
                if body.get("errorMessage"):
                    print(f"  DIAG  errorMessage: {_truncate(body['errorMessage'])}")
            return job_status


# ---------------------------------------------------------------------------
# Cleanup (always runs if a case was created; failure is secondary warning)
# ---------------------------------------------------------------------------

def _cleanup(case_id: str | None, base: str, token: str | None, skip: bool) -> None:
    _step(7, "Archive case (cleanup)")
    if not case_id:
        print("  SKIP  no case was created")
        return
    if skip:
        print(f"  SKIP  --skip-cleanup set — case {case_id!r} left in database")
        return

    endpoint = f"{base}/cases/{case_id}/archive"
    http_status, body = _request("POST", endpoint, b"", token=token)
    if http_status == 200:
        # Housekeeping — does not count in _passed/_failed
        print(f"  OK    case archived  id={case_id!r}")
    else:
        # Secondary warning — deliberately does not call fail() to avoid
        # overwriting the main flow result with a cleanup issue
        print(f"  WARN  archive returned {http_status} — case {case_id!r} may remain in DB")
        if body:
            print(f"        response: {_truncate(body)}")


# ---------------------------------------------------------------------------
# Flow steps (separate function so try/finally guarantees cleanup,
# while main() always prints the summary)
# ---------------------------------------------------------------------------

def _run_flow(base: str, email: str, skip_cleanup: bool, ts: str, token_ref: list) -> None:
    """
    Execute steps 1–7. Uses try/finally to guarantee cleanup runs.
    Early return on fatal errors; cleanup fires via finally in all cases.
    token_ref is a one-element list so the token can be passed to cleanup
    even when early-exit happens before the outer scope sees it.
    """
    token: str | None = None

    try:
        # ── Step 1: Login ──────────────────────────────────────────────────
        _step(1, "Login")
        endpoint = f"{base}/auth/login"
        # Password is read from token_ref[1] and sent to the API — never printed
        http_status, body = _request(
            "POST", endpoint,
            json.dumps({"email": email, "password": token_ref[1]}).encode(),
        )
        if http_status != 200 or not isinstance(body, dict) or not body.get("accessToken"):
            fail("login", f"POST /auth/login → {http_status}")
            _diag("login failed", endpoint, http_status, _safe_body(body))
            return  # finally: cleanup skipped (no case yet)
        token = body["accessToken"]
        token_ref[0] = token
        user_info = body.get("user") or {}
        user_email = user_info.get("email", email) if isinstance(user_info, dict) else email
        ok("authenticated", f"user={user_email}")

        # ── Step 2: Create case ────────────────────────────────────────────
        _step(2, "Create case")
        endpoint = f"{base}/cases"
        http_status, body = _request(
            "POST", endpoint,
            json.dumps({
                "title": f"{TEST_TITLE_PREFIX} {ts}",
                "description": "Automated flow test — safe to archive",
                "propertyType": "house",
                "repairScope": "full_reconstruction",
            }).encode(),
            token=token,
        )
        if http_status != 201 or not isinstance(body, dict) or not body.get("id"):
            fail("create case", f"POST /cases → {http_status}")
            _diag("create case failed", endpoint, http_status, body)
            return  # finally: cleanup skipped (no case yet)
        _ctx["case_id"] = body["id"]
        ok("case created", f"id={_ctx['case_id']}")

        # ── Step 3: Fetch case ─────────────────────────────────────────────
        _step(3, "Fetch case")
        endpoint = f"{base}/cases/{_ctx['case_id']}"
        http_status, body = _request("GET", endpoint, token=token)
        if http_status != 200 or not isinstance(body, dict):
            fail("fetch case", f"GET /cases/{_ctx['case_id']} → {http_status}")
            _diag("fetch case failed", endpoint, http_status, body)
            # non-fatal — continue to trigger job
        elif body.get("id") != _ctx["case_id"]:
            fail("case id matches", f"expected {_ctx['case_id']!r}, got {body.get('id')!r}")
        else:
            ok("case fetched", f"status={body.get('status')}")

        # ── Step 4: Trigger analysis job ──────────────────────────────────
        _step(4, "Trigger analysis job")
        endpoint = f"{base}/cases/{_ctx['case_id']}/analysis-jobs"
        http_status, body = _request("POST", endpoint, b"", token=token)
        if http_status not in (200, 202) or not isinstance(body, dict) or not body.get("jobId"):
            fail("trigger job", f"POST .../analysis-jobs → {http_status}")
            _diag("trigger job failed", endpoint, http_status, body)
            return  # finally: cleanup will archive the case
        _ctx["job_id"] = body["jobId"]
        provider = body.get("provider") or "unknown"
        ok("job triggered", f"jobId={_ctx['job_id']}  provider={provider}")
        if provider not in ("mock", "unknown"):
            print(f"  WARN  provider={provider!r} — real AI calls may be slow or require API keys")

        # ── Step 5: Poll job ───────────────────────────────────────────────
        _step(5, f"Poll job (max {POLL_MAX_WAIT}s, interval {POLL_INTERVAL}s)")
        job_status = _poll_job(f"{base}/analysis-jobs/{_ctx['job_id']}", token=token)
        _ctx["last_job_status"] = job_status

        # ── Step 6: Verify result ──────────────────────────────────────────
        _step(6, "Verify analysis result")
        if job_status != "completed":
            print(f"  SKIP  job status={job_status!r} — cannot verify latestAnalysis")
        else:
            endpoint = f"{base}/cases/{_ctx['case_id']}"
            http_status, body = _request("GET", endpoint, token=token)
            if http_status != 200 or not isinstance(body, dict):
                fail("verify result", f"GET /cases/{_ctx['case_id']} → {http_status}")
                _diag("fetch case for result check failed", endpoint, http_status, body)
            elif body.get("latestAnalysis") is not None:
                ok("latestAnalysis present on case")
            else:
                fail("latestAnalysis present on case", "field is null after completed job")
                _diag("latestAnalysis missing", endpoint, http_status, None)

    finally:
        # Step 7 always runs when a case was created — even on early return / exception
        _cleanup(_ctx.get("case_id"), base, token_ref[0], skip_cleanup)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Critical business flow smoke test")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL (default: %(default)s)")
    parser.add_argument(
        "--email",
        default=os.getenv("NOVU_TEST_EMAIL", "").strip(),
        help="Test user email (or set NOVU_TEST_EMAIL)",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("NOVU_TEST_PASSWORD", "").strip(),
        help="Test user password (or set NOVU_TEST_PASSWORD)",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Leave the test case in the database (useful for manual inspection)",
    )
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/api/v1"

    if not args.email or not args.password:
        print(
            "SKIP: credentials not available — set NOVU_TEST_EMAIL / NOVU_TEST_PASSWORD "
            "or pass --email / --password"
        )
        sys.exit(2)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    print(f"Business flow: {base}")
    print(f"User:          {args.email}")
    print(f"Case title:    {TEST_TITLE_PREFIX} {ts}")

    # token_ref[0] = resolved token (for cleanup)
    # token_ref[1] = password (passed into _run_flow to avoid storing in outer scope)
    token_ref = [None, args.password]

    _run_flow(base, args.email, args.skip_cleanup, ts, token_ref)

    # Summary always runs — _run_flow uses try/finally internally
    total = _passed + _failed
    print(f"\n{_passed}/{total} passed")
    if _failed:
        print("FAIL: one or more flow steps failed — see output above")
        sys.exit(1)


if __name__ == "__main__":
    main()
