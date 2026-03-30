from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_auth_smoke
import verify_core_api_smoke
import verify_deploy
import verify_http_probes
import verify_release_gate


class _StubHandler(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, object]] = {}

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _handle(self) -> None:
        status, payload = self.routes.get((self.command, self.path), (404, {"detail": "not found"}))
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))

        if self.command == "POST" and self.path == "/api/v1/auth/login" and payload == "__dynamic_login__":
            body = raw.decode("utf-8")
            if "manager_a@test.local" in body and "TestPassA1!" in body:
                status = 200
                payload = {"accessToken": "stub-token"}
            else:
                status = 401
                payload = {"detail": "bad credentials"}

        if self.command == "GET" and self.path == "/api/v1/auth/me" and payload == "__dynamic_me__":
            auth = self.headers.get("Authorization", "")
            if auth == "Bearer stub-token":
                status = 200
                payload = {"email": "manager_a@test.local"}
            elif auth == "Bearer invalid.jwt.token":
                status = 401
                payload = {"detail": "invalid token"}
            else:
                status = 401
                payload = {"detail": "missing token"}

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(_json_bytes(payload))


@pytest.fixture
def stub_server():
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield server, base_url
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_verify_http_probes_success_for_ready_service(stub_server):
    server, base_url = stub_server
    server.RequestHandlerClass.routes = {
        ("GET", "/api/v1/health"): (200, {"status": "ok", "service": "python-backend"}),
        ("GET", "/api/v1/ready"): (200, {"status": "ready", "service": "python-backend"}),
    }

    assert verify_http_probes.main(["--base-url", base_url]) == 0


def test_verify_http_probes_fails_when_readiness_is_not_ready(stub_server):
    server, base_url = stub_server
    server.RequestHandlerClass.routes = {
        ("GET", "/api/v1/health"): (200, {"status": "ok", "service": "python-backend"}),
        ("GET", "/api/v1/ready"): (503, {"status": "not_ready", "service": "python-backend"}),
    }

    assert verify_http_probes.main(["--base-url", base_url]) == 1
    assert verify_http_probes.main(["--base-url", base_url, "--allow-not-ready"]) == 0


def test_verify_auth_smoke_returns_skip_without_credentials():
    assert verify_auth_smoke.main([]) == 2


def test_verify_auth_smoke_success_with_valid_credentials(stub_server):
    server, base_url = stub_server
    server.RequestHandlerClass.routes = {
        ("GET", "/api/v1/auth/me"): (200, "__dynamic_me__"),
        ("POST", "/api/v1/auth/login"): (200, "__dynamic_login__"),
    }

    assert (
        verify_auth_smoke.main(
            [
                "--base-url",
                base_url,
                "--email",
                "manager_a@test.local",
                "--password",
                "TestPassA1!",
            ]
        )
        == 0
    )


def test_verify_core_api_smoke_success_with_valid_credentials(stub_server):
    server, base_url = stub_server
    server.RequestHandlerClass.routes = {
        ("POST", "/api/v1/auth/login"): (200, "__dynamic_login__"),
        ("GET", "/api/v1/cases"): (200, {"items": [{"id": "case-1"}], "total": 1, "next_cursor": None}),
        ("GET", "/api/v1/cases/case-1"): (200, {"id": "case-1"}),
        ("GET", "/api/v1/pricebooks"): (200, {"items": [{"id": "pb-1"}]}),
        ("GET", "/api/v1/material-catalog"): (200, {"items": [{"id": "mat-1"}]}),
    }

    assert (
        verify_core_api_smoke.main(
            [
                "--base-url",
                base_url,
                "--email",
                "manager_a@test.local",
                "--password",
                "TestPassA1!",
            ]
        )
        == 0
    )


def test_verify_deploy_propagates_probe_failure(monkeypatch):
    monkeypatch.setattr(
        verify_deploy,
        "run_probe_verification",
        lambda **kwargs: [verify_deploy.CheckResult("probe failed", False, "boom")],
    )
    monkeypatch.setattr(
        verify_deploy,
        "run_auth_verification",
        lambda **kwargs: [verify_deploy.CheckResult("auth should not run", True)],
    )

    assert verify_deploy.main(["--base-url", "http://127.0.0.1:8000"]) == 1


def test_verify_deploy_requires_auth_when_requested(monkeypatch):
    monkeypatch.setattr(
        verify_deploy,
        "run_probe_verification",
        lambda **kwargs: [verify_deploy.CheckResult("probes ok", True)],
    )

    assert verify_deploy.main(["--base-url", "http://127.0.0.1:8000", "--require-auth"]) == 1


def test_verify_deploy_runs_auth_when_credentials_are_present(monkeypatch):
    monkeypatch.setattr(
        verify_deploy,
        "run_probe_verification",
        lambda **kwargs: [verify_deploy.CheckResult("probes ok", True)],
    )
    monkeypatch.setattr(
        verify_deploy,
        "run_auth_verification",
        lambda **kwargs: [verify_deploy.CheckResult("auth ok", True)],
    )
    monkeypatch.setattr(
        verify_deploy,
        "run_core_api_verification",
        lambda **kwargs: [verify_deploy.CheckResult("api smoke ok", True)],
    )

    assert (
        verify_deploy.main(
            [
                "--base-url",
                "http://127.0.0.1:8000",
                "--auth-email",
                "ops@example.com",
                "--auth-password",
                "secret",
            ]
        )
        == 0
    )


def test_verify_deploy_propagates_api_smoke_failure(monkeypatch):
    monkeypatch.setattr(
        verify_deploy,
        "run_probe_verification",
        lambda **kwargs: [verify_deploy.CheckResult("probes ok", True)],
    )
    monkeypatch.setattr(
        verify_deploy,
        "run_auth_verification",
        lambda **kwargs: [verify_deploy.CheckResult("auth ok", True)],
    )
    monkeypatch.setattr(
        verify_deploy,
        "run_core_api_verification",
        lambda **kwargs: [verify_deploy.CheckResult("api smoke failed", False, "boom")],
    )

    assert (
        verify_deploy.main(
            [
                "--base-url",
                "http://127.0.0.1:8000",
                "--auth-email",
                "ops@example.com",
                "--auth-password",
                "secret",
            ]
        )
        == 1
    )


def test_verify_release_gate_stops_before_migration_when_preflight_fails(monkeypatch):
    monkeypatch.setattr(
        verify_release_gate,
        "run_import_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("imports failed", False, "boom")],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_fail_fast_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("fail-fast ok", True)],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "_run_command",
        lambda **kwargs: pytest.fail("migration command must not run after failed preflight"),
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_deploy_verification",
        lambda **kwargs: pytest.fail("deploy verification must not run after failed preflight"),
    )

    results = verify_release_gate.run_release_gate(
        backend_root=REPO_ROOT,
        python_executable=sys.executable,
        base_url="http://127.0.0.1:8000",
        timeout=5,
        skip_import_startup=False,
        skip_fail_fast=False,
        apply_migrations=True,
        auth_email="",
        auth_password="",
        require_auth=False,
        skip_auth=False,
        skip_api_smoke=False,
        allow_not_ready=False,
    )

    assert verify_release_gate.all_ok(results) is False
    assert results[0].name == "imports failed"


def test_verify_release_gate_stops_before_deploy_when_migration_fails(monkeypatch):
    monkeypatch.setattr(
        verify_release_gate,
        "run_import_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("imports ok", True)],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_fail_fast_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("fail-fast ok", True)],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "_run_command",
        lambda **kwargs: verify_release_gate.CheckResult("alembic upgrade head", False, "migration failed"),
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_deploy_verification",
        lambda **kwargs: pytest.fail("deploy verification must not run after failed migration"),
    )

    results = verify_release_gate.run_release_gate(
        backend_root=REPO_ROOT,
        python_executable=sys.executable,
        base_url="http://127.0.0.1:8000",
        timeout=5,
        skip_import_startup=False,
        skip_fail_fast=False,
        apply_migrations=True,
        auth_email="",
        auth_password="",
        require_auth=False,
        skip_auth=False,
        skip_api_smoke=False,
        allow_not_ready=False,
    )

    assert [result.ok for result in results] == [True, True, False]
    assert results[-1].name == "alembic upgrade head"


def test_verify_release_gate_runs_deploy_bundle_after_successful_preflight(monkeypatch):
    monkeypatch.setattr(
        verify_release_gate,
        "run_import_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("imports ok", True)],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_fail_fast_checks",
        lambda **kwargs: [verify_release_gate.CheckResult("fail-fast ok", True)],
    )
    monkeypatch.setattr(
        verify_release_gate,
        "_run_command",
        lambda **kwargs: verify_release_gate.CheckResult("alembic upgrade head", True),
    )
    monkeypatch.setattr(
        verify_release_gate,
        "run_deploy_verification",
        lambda **kwargs: [verify_release_gate.CheckResult("deploy ok", True)],
    )

    results = verify_release_gate.run_release_gate(
        backend_root=REPO_ROOT,
        python_executable=sys.executable,
        base_url="http://127.0.0.1:8000",
        timeout=5,
        skip_import_startup=False,
        skip_fail_fast=False,
        apply_migrations=True,
        auth_email="ops@example.com",
        auth_password="secret",
        require_auth=False,
        skip_auth=False,
        skip_api_smoke=False,
        allow_not_ready=False,
    )

    assert verify_release_gate.all_ok(results) is True
    assert [result.name for result in results] == [
        "imports ok",
        "fail-fast ok",
        "alembic upgrade head",
        "deploy ok",
    ]


def _json_bytes(payload: object) -> bytes:
    import json

    return json.dumps(payload).encode("utf-8")
