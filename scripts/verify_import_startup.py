from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
BACKEND_ROOT = REPO_ROOT / "python-backend"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verification_common import CheckResult, all_ok, print_results

IMPORT_CHECKS = [
    ("app.core.config", "settings and env parsing"),
    ("app.core.logging", "logging configuration"),
    ("app.db.base", "SQLAlchemy declarative base"),
    ("app.db.session", "engine and session factory"),
    ("app.models", "domain models"),
    ("app.api.router", "routes, services, repositories and schemas"),
    ("app.main", "application entrypoint"),
]

_PROD_JWT = "a-very-strong-jwt-secret-for-smoke-check-123456"
_PROD_REDIS = "redis://:a-strong-redis-password-xyz123@localhost:6379/0"
_PROD_METRICS = "a-strong-metrics-token-for-smoke-check-123456789"
_PROD_DB_ASYNC = "postgresql+asyncpg://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"
_PROD_DB_SYNC = "postgresql://novu:Str0ngP%40ssw0rd!@localhost:5432/novu_prod"
_PROD_BASE_URL = "https://app.novu-builder.com"
_PROD_CORS = "https://app.novu-builder.com"
_PROD_S3_BUCKET = "novu-production-bucket"


def run_import_checks(*, backend_root: Path) -> list[CheckResult]:
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    results: list[CheckResult] = []

    for module_name, description in IMPORT_CHECKS:
        try:
            importlib.import_module(module_name)
            if module_name == "app.main":
                from fastapi import FastAPI
                from app.main import app

                if not isinstance(app, FastAPI):
                    raise TypeError(f"app.main.app is {type(app)!r}, expected FastAPI")
            results.append(CheckResult(f"import {module_name} ({description})", True))
        except Exception as exc:
            results.append(CheckResult(f"import {module_name} ({description})", False, f"{type(exc).__name__}: {exc}"))

    return results


def run_fail_fast_checks(
    *,
    backend_root: Path,
    python_executable: str,
    timeout: int,
) -> list[CheckResult]:
    results = [
        _run_settings_subprocess_check(
            name="production config accepts a valid strong baseline",
            backend_root=backend_root,
            python_executable=python_executable,
            timeout=timeout,
            overrides={},
            expect_success=True,
        ),
        _run_settings_subprocess_check(
            name="production config rejects default JWT secret",
            backend_root=backend_root,
            python_executable=python_executable,
            timeout=timeout,
            overrides={"JWT_SECRET": "dev-secret-change-me"},
            expect_success=False,
            expected_fragment="JWT_SECRET",
        ),
        _run_settings_subprocess_check(
            name="production config rejects empty REDIS_URL",
            backend_root=backend_root,
            python_executable=python_executable,
            timeout=timeout,
            overrides={"REDIS_URL": ""},
            expect_success=False,
            expected_fragment="REDIS_URL",
        ),
        _run_settings_subprocess_check(
            name="production config rejects disabled metrics auth",
            backend_root=backend_root,
            python_executable=python_executable,
            timeout=timeout,
            overrides={"METRICS_AUTH_ENABLED": "false"},
            expect_success=False,
            expected_fragment="METRICS_AUTH_ENABLED",
        ),
    ]
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify import/startup viability and representative production fail-fast config guards."
    )
    parser.add_argument(
        "--backend-root",
        default=str(BACKEND_ROOT),
        help="Path to python-backend directory (default: %(default)s)",
    )
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for subprocess fail-fast checks (default: current interpreter)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Timeout for subprocess validation checks in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-fail-fast",
        action="store_true",
        help="Only run import smoke and skip representative production fail-fast checks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backend_root = Path(args.backend_root).resolve()
    if not backend_root.exists():
        print_results(
            [CheckResult("backend root exists", False, str(backend_root))],
            title="Import and startup verification",
        )
        return 1

    results = run_import_checks(backend_root=backend_root)
    if not args.skip_fail_fast:
        results.extend(
            run_fail_fast_checks(
                backend_root=backend_root,
                python_executable=args.python_executable,
                timeout=args.timeout,
            )
        )

    print_results(results, title="Import and startup verification")
    return 0 if all_ok(results) else 1


def _run_settings_subprocess_check(
    *,
    name: str,
    backend_root: Path,
    python_executable: str,
    timeout: int,
    overrides: dict[str, str],
    expect_success: bool,
    expected_fragment: str | None = None,
) -> CheckResult:
    env = os.environ.copy()
    env.update(_valid_production_env())
    env.update(overrides)
    command = [
        python_executable,
        "-c",
        "from app.core.config import Settings; Settings(); print('settings-ok')",
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=str(backend_root),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(name, False, f"timed out after {timeout}s")

    combined_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()

    if expect_success:
        if completed.returncode == 0 and "settings-ok" in combined_output:
            return CheckResult(name, True)
        return CheckResult(
            name,
            False,
            combined_output or f"unexpected exit code {completed.returncode}",
        )

    if completed.returncode == 0:
        return CheckResult(name, False, "invalid configuration unexpectedly succeeded")
    if expected_fragment and expected_fragment not in combined_output:
        return CheckResult(name, False, combined_output or "expected validation failure fragment missing")
    return CheckResult(name, True)


def _valid_production_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "JWT_SECRET": _PROD_JWT,
        "REDIS_URL": _PROD_REDIS,
        "REDIS_FAILOVER_URLS": "",
        "REDIS_SOCKET_CONNECT_TIMEOUT": "1.0",
        "REDIS_SOCKET_TIMEOUT": "1.0",
        "REDIS_HEALTH_CHECK_INTERVAL": "30",
        "REDIS_RETRY_ATTEMPTS": "3",
        "REDIS_RETRY_BACKOFF_BASE": "0.05",
        "REDIS_RETRY_BACKOFF_CAP": "0.5",
        "METRICS_AUTH_ENABLED": "true",
        "METRICS_AUTH_TOKEN": _PROD_METRICS,
        "DATABASE_URL": _PROD_DB_ASYNC,
        "DATABASE_URL_SYNC": _PROD_DB_SYNC,
        "DB_POOL_SIZE": "10",
        "DB_MAX_OVERFLOW": "10",
        "DB_POOL_TIMEOUT": "30",
        "DB_POOL_RECYCLE": "1800",
        "APP_BASE_URL": _PROD_BASE_URL,
        "CORS_ALLOWED_ORIGINS": _PROD_CORS,
        "AI_ANALYSIS_PROVIDER": "mock",
        "WORKER_CONCURRENCY": "2",
        "WORKER_HEAVY_CONCURRENCY": "1",
        "WORKER_JOB_LEASE_TIMEOUT_SECONDS": "600",
        "WORKER_HEAVY_JOB_LEASE_TIMEOUT_SECONDS": "1800",
        "WORKER_JOB_REAP_INTERVAL_SECONDS": "30",
        "WORKER_HEAVY_JOB_REAP_INTERVAL_SECONDS": "30",
        "READINESS_PROCESSING_GRACE_SECONDS": "75",
        "ANALYSIS_QUEUE_MAX_DEPTH": "100",
        "HEAVY_QUEUE_MAX_DEPTH": "50",
        "BACKPRESSURE_MAX_CONCURRENT_JOBS": "3",
        "BACKPRESSURE_MAX_QUEUED_JOBS": "200",
        "BACKPRESSURE_MAX_RETRY_INFLIGHT": "20",
        "ANALYSIS_JOB_MAX_ATTEMPTS": "3",
        "ANALYSIS_RETRY_BACKOFF_BASE_SECONDS": "30",
        "ANALYSIS_RETRY_BACKOFF_MAX_SECONDS": "300",
        "ANALYSIS_JOBS_PER_TENANT_LIMIT": "10",
        "WORKER_DB_POOL_SIZE": "0",
        "WORKER_DB_POOL_TIMEOUT": "30",
        "WORKER_INSTANCE_COUNT": "1",
        "RATE_LIMIT_ADMIN_WRITE": "10/minute",
        "RATE_LIMIT_ADMIN_SENSITIVE": "5/minute",
        "RATE_LIMIT_UPLOAD": "30/minute",
        "RATE_LIMIT_ANALYSIS_JOBS": "20/minute",
        "RATE_LIMIT_MARKER_WRITE": "30/minute",
        "RATE_LIMIT_READ_LIST": "120/minute",
        "RATE_LIMIT_READ_DETAIL": "60/minute",
        "STORAGE_BACKEND": "s3",
        "STORAGE_AUTHORITATIVE": "true",
        "S3_BUCKET": _PROD_S3_BUCKET,
        "S3_REGION": "us-east-1",
        "S3_CONNECT_TIMEOUT_SECONDS": "3",
        "S3_READ_TIMEOUT_SECONDS": "10",
        "STORAGE_SIGNED_URL_TTL_SECONDS": "3600",
        "EXPORT_TTL_DAYS": "7",
        "WORKER_METRICS_ENABLED": "true",
        "WORKER_METRICS_HOST": "0.0.0.0",
        "WORKER_METRICS_PORT": "9101",
        "SENTRY_DSN": "",
        "SENTRY_TRACES_SAMPLE_RATE": "0.05",
        "SENTRY_PROFILES_SAMPLE_RATE": "0.0",
    }


if __name__ == "__main__":
    sys.exit(main())
