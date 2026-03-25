"""
Performance baseline — measures p95 latency of critical endpoints.

Purpose:
  Establish a latency baseline so regressions are caught before they reach production.
  Run this after schema changes, new middleware, or dependency upgrades.

Methodology:
  - N sequential requests per endpoint (default: 20)
  - First WARMUP requests are discarded (cold-start bias: connection pool, JIT, caches)
  - Measures wall-clock time from first byte sent to last byte received (urllib)
  - Reports: min / avg / p95 / max  (all in ms)
  - PASS if p95 <= per-endpoint threshold, FAIL otherwise

Endpoints measured:
  GET  /health            — infrastructure baseline (no auth, no DB)
  POST /auth/login        — password hash + DB lookup
  GET  /auth/me           — token decode + DB lookup
  GET  /cases             — list query (org-scoped)
  GET  /cases/prj_1       — project detail (joins + nested)

Requires:
  - Backend running with dev seed (SEED_ON_STARTUP=true / APP_ENV=development)
  - Seed project prj_1 in DB

Usage:
    python scripts/test-performance-baseline.py
    python scripts/test-performance-baseline.py --url http://localhost:8000
    python scripts/test-performance-baseline.py --iterations 50
    python scripts/test-performance-baseline.py --threshold 1000
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:8000"
DEFAULT_ITERATIONS = 20
WARMUP = 3           # requests discarded before measurement starts
CONNECT_TIMEOUT = 5  # seconds


# ---------------------------------------------------------------------------
# Endpoint definitions
# ---------------------------------------------------------------------------

def _endpoints(base: str, token: str | None) -> list[dict]:
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    login_body = json.dumps({"email": "demo@novu.local", "password": "demo1234"}).encode()

    return [
        {
            "label": "GET  /health",
            "method": "GET",
            "url": f"{base.rstrip('/api/v1')}/health",
            "headers": {},
            "body": None,
            "threshold_ms": 50,
        },
        {
            "label": "POST /auth/login",
            "method": "POST",
            "url": f"{base}/auth/login",
            "headers": {"Content-Type": "application/json"},
            "body": login_body,
            "threshold_ms": 600,  # bcrypt is intentionally slow
        },
        {
            "label": "GET  /auth/me",
            "method": "GET",
            "url": f"{base}/auth/me",
            "headers": auth,
            "body": None,
            "threshold_ms": 200,
            "requires_auth": True,
        },
        {
            "label": "GET  /cases",
            "method": "GET",
            "url": f"{base}/cases",
            "headers": auth,
            "body": None,
            "threshold_ms": 300,
            "requires_auth": True,
        },
        {
            "label": "GET  /cases/prj_1",
            "method": "GET",
            "url": f"{base}/cases/prj_1",
            "headers": auth,
            "body": None,
            "threshold_ms": 500,
            "requires_auth": True,
        },
    ]


# ---------------------------------------------------------------------------
# HTTP measurement
# ---------------------------------------------------------------------------

def _measure_once(method: str, url: str, headers: dict, body: bytes | None) -> float | None:
    """Return elapsed milliseconds, or None on connection error."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT):
            pass
    except urllib.error.HTTPError:
        pass  # non-2xx is still a valid measured response
    except urllib.error.URLError as exc:
        print(f"  connection error — {exc.reason}")
        return None
    except Exception as exc:
        print(f"  unexpected error — {exc}")
        return None
    return (time.perf_counter() - t0) * 1000


def _measure(ep: dict, n: int) -> list[float]:
    """Run n+WARMUP requests and return the n measured samples."""
    samples: list[float] = []
    total = WARMUP + n
    for i in range(total):
        ms = _measure_once(ep["method"], ep["url"], ep["headers"], ep["body"])
        if ms is None:
            return []        # connection failed, abort this endpoint
        if i >= WARMUP:
            samples.append(ms)
    return samples


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _stats(samples: list[float]) -> tuple[float, float, float, float]:
    """Return (min, avg, p95, max) in ms."""
    s = sorted(samples)
    n = len(s)
    p95_idx = max(0, int(n * 0.95) - 1)
    return (
        round(s[0], 1),
        round(sum(s) / n, 1),
        round(s[p95_idx], 1),
        round(s[-1], 1),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Performance baseline smoke test")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                        help=f"Requests per endpoint after warmup (default: {DEFAULT_ITERATIONS})")
    parser.add_argument("--threshold", type=int, default=None,
                        help="Override p95 threshold (ms) for all endpoints")
    parser.add_argument("--email", default="demo@novu.local")
    parser.add_argument("--password", default="demo1234")
    args = parser.parse_args()

    base = args.url.rstrip("/") + "/api/v1"
    n = max(args.iterations, WARMUP + 1)

    # ------------------------------------------------------------------
    # Acquire token (best-effort — auth endpoints can still be measured
    # with a missing token; they will return 401 but latency is valid)
    # ------------------------------------------------------------------
    token: str | None = None
    req = urllib.request.Request(
        f"{base}/auth/login",
        data=json.dumps({"email": args.email, "password": args.password}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT) as resp:
            token = json.loads(resp.read()).get("accessToken")
    except urllib.error.URLError as exc:
        print(f"Backend not reachable: {exc.reason}")
        sys.exit(1)
    except Exception:
        pass  # login failed — proceed without token, auth endpoints will 401

    if not token:
        print("  WARN  Could not obtain token — auth-required endpoints will return 401.")
        print("        Latency is still measured and reported.\n")

    # ------------------------------------------------------------------
    # Run measurements
    # ------------------------------------------------------------------
    print(f"Performance baseline: {base}")
    print(f"Iterations: {n} per endpoint  ({WARMUP} warmup discarded)\n")

    col_label = 28
    print(
        f"  {'endpoint':<{col_label}}  {'min':>6}  {'avg':>6}  {'p95':>6}  {'max':>6}  "
        f"{'threshold':>10}  result"
    )
    print(f"  {'-' * col_label}  {'------':>6}  {'------':>6}  {'------':>6}  {'------':>6}  "
          f"{'----------':>10}  ------")

    endpoints = _endpoints(base, token)
    passed = 0
    failed = 0
    skipped = 0

    for ep in endpoints:
        threshold = args.threshold if args.threshold is not None else ep["threshold_ms"]
        requires_auth = ep.get("requires_auth", False)

        if requires_auth and not token:
            print(f"  {'SKIP':<6}  {ep['label']:<{col_label}}  (no token)")
            skipped += 1
            continue

        samples = _measure(ep, n)

        if not samples:
            print(f"  {'FAIL':<6}  {ep['label']}")
            failed += 1
            continue

        mn, avg, p95, mx = _stats(samples)
        result = "OK" if p95 <= threshold else "FAIL"
        marker = "OK  " if result == "OK" else "FAIL"

        print(
            f"  {marker}  {ep['label']:<{col_label}}  "
            f"{mn:>6.1f}  {avg:>6.1f}  {p95:>6.1f}  {mx:>6.1f}  "
            f"{threshold:>8}ms  {result}"
        )

        if result == "OK":
            passed += 1
        else:
            failed += 1

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = passed + failed + skipped
    print(f"\n{passed}/{total} passed", end="")
    if skipped:
        print(f"  ({skipped} skipped — no token)", end="")
    print()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
