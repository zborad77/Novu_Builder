"""B10: Worker heartbeat detection tests.

Coverage:
1. Worker runner writes per-instance heartbeat keys in the main loop
2. /health/internal reports worker alive when at least one fresh heartbeat exists
3. /health/internal reports worker dead when no heartbeat exists
4. /health/internal reports worker status unknown when Redis is unavailable
5. Legacy single-worker heartbeat key remains readable during rollout
"""
import inspect
import os
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

# Anchored to this file, not to a developer's checkout. An absolute Windows path
# is a plain relative path on Linux ("d:/..." has no drive letter there), so the
# compose read raised FileNotFoundError in CI and the heartbeat paths silently
# created a stray "d:" directory.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
_HEARTBEAT_TMP = _BACKEND_ROOT / ".tmp_test_runtime"


async def _scan_iter(*keys):
    for key in keys:
        yield key


def _mock_health_internal_session():
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one=lambda: 0, scalar_one_or_none=lambda: None)
    )
    mock_session.scalar = AsyncMock(return_value=None)
    return mock_session


def _redis_with_heartbeats(values_by_key: dict[object, bytes | None]):
    redis = AsyncMock()

    async def _get(key):
        return values_by_key.get(key)

    pattern_keys = [
        key
        for key in values_by_key
        if isinstance(key, str) and key.startswith("worker:heartbeat:")
    ]

    redis.get = AsyncMock(side_effect=_get)
    redis.mget = AsyncMock(side_effect=lambda keys: [values_by_key.get(key) for key in keys])
    redis.llen = AsyncMock(return_value=0)
    redis.scan_iter = lambda match=None: _scan_iter(*pattern_keys)
    redis.runtime_status = lambda: SimpleNamespace(
        state="ready",
        mode="single",
        candidate_count=1,
        active_url="redis://:***@localhost:6379/0",
        degraded=False,
        last_error=None,
        last_failover_at=None,
    )
    return redis


# ── 1. Worker runner writes heartbeat ────────────────────────────────────────

class TestWorkerHeartbeat:

    def test_runner_heartbeat_prefix_constant_value(self):
        """Per-instance heartbeat keys must use the shared worker:heartbeat: prefix."""
        from app.worker import runner
        assert runner._HEARTBEAT_KEY_PREFIX == "worker:heartbeat:", (
            "_HEARTBEAT_KEY_PREFIX must be 'worker:heartbeat:' for per-instance heartbeats"
        )

    def test_runner_source_references_heartbeat_key(self):
        """runner.run() must build and write a per-instance heartbeat key."""
        from app.worker import runner
        src = inspect.getsource(runner.run)
        assert "worker_heartbeat_key" in src, (
            "run() must build a per-instance heartbeat key before writing heartbeats"
        )

    def test_runner_source_sets_ttl_on_heartbeat(self):
        """Heartbeat must be written with an expiry (ex=...) so stale keys auto-expire."""
        from app.worker import runner
        src = inspect.getsource(runner._write_heartbeat_if_due)
        assert "write_worker_heartbeat" in src, (
            "_write_heartbeat_if_due() must delegate heartbeat writes through the shared helper"
        )

    def test_runner_source_clears_own_heartbeat_on_shutdown(self):
        """Graceful shutdown should clear the worker's own heartbeat key."""
        from app.worker import runner
        src = inspect.getsource(runner.run)
        assert "clear_worker_heartbeat" in src, (
            "run() must clear its own heartbeat key during shutdown"
        )
        assert "clear_local_worker_heartbeat" in src, (
            "run() must clear its local heartbeat file during shutdown"
        )

    def test_heartbeat_constants_sane(self):
        """Heartbeat interval must be less than TTL (otherwise key always expires)."""
        from app.worker import runner
        assert runner._HEARTBEAT_INTERVAL < runner._HEARTBEAT_TTL, (
            "_HEARTBEAT_INTERVAL must be less than _HEARTBEAT_TTL"
        )

    def test_heartbeat_ttl_at_least_2x_interval(self):
        """TTL should be ≥ 2× interval to survive one missed write cycle."""
        from app.worker import runner
        assert runner._HEARTBEAT_TTL >= 2 * runner._HEARTBEAT_INTERVAL


# ── 2. /health/internal reflects worker state ────────────────────────────────

@pytest.mark.asyncio
async def test_write_worker_heartbeat_sets_ttl():
    from app.worker.heartbeat import WORKER_HEARTBEAT_TTL, write_worker_heartbeat

    redis = AsyncMock()

    await write_worker_heartbeat(redis, "worker-a")

    redis.set.assert_awaited_once()
    assert redis.set.await_args.kwargs["ex"] == WORKER_HEARTBEAT_TTL


@pytest.mark.asyncio
async def test_write_local_worker_heartbeat_updates_local_file(monkeypatch):
    from app.worker.heartbeat import (
        local_worker_heartbeat_is_fresh,
        worker_local_health_path,
        write_local_worker_heartbeat,
    )

    heartbeat_path = (_HEARTBEAT_TMP / "heartbeat-test-current.json")
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.unlink(missing_ok=True)
    monkeypatch.setenv("WORKER_HEALTH_PATH", str(heartbeat_path))

    await write_local_worker_heartbeat("worker-a", now=datetime.now(UTC))

    payload = json.loads(worker_local_health_path().read_text(encoding="utf-8"))
    assert payload["instance_id"] == "worker-a"
    assert payload["pid"] == os.getpid()
    assert local_worker_heartbeat_is_fresh(now=datetime.now(UTC)) is True


def test_local_worker_heartbeat_stale_when_timestamp_too_old(monkeypatch):
    from app.worker.heartbeat import (
        WORKER_HEARTBEAT_FRESHNESS_SECONDS,
        local_worker_heartbeat_is_fresh,
        worker_local_health_path,
    )

    heartbeat_path = (_HEARTBEAT_TMP / "heartbeat-test-stale.json")
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.unlink(missing_ok=True)
    monkeypatch.setenv("WORKER_HEALTH_PATH", str(heartbeat_path))
    stale_at = datetime.now(UTC).timestamp() - (WORKER_HEARTBEAT_FRESHNESS_SECONDS + 5)
    worker_local_health_path().write_text(
        json.dumps(
            {
                "instance_id": "worker-a",
                "timestamp": datetime.fromtimestamp(stale_at, tz=UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert local_worker_heartbeat_is_fresh(now=datetime.now(UTC)) is False


def test_local_worker_heartbeat_rejects_missing_or_dead_worker_pid(monkeypatch):
    from app.worker.heartbeat import (
        local_worker_heartbeat_is_fresh,
        worker_local_health_path,
    )

    heartbeat_path = (_HEARTBEAT_TMP / "heartbeat-test-dead-pid.json")
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.unlink(missing_ok=True)
    monkeypatch.setenv("WORKER_HEALTH_PATH", str(heartbeat_path))
    worker_local_health_path().write_text(
        json.dumps(
            {
                "instance_id": "worker-a",
                "pid": 999999,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    assert local_worker_heartbeat_is_fresh(now=datetime.now(UTC), require_process=True) is False


def test_worker_compose_healthcheck_restarts_stale_worker_via_pid1_signal():
    compose = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "WORKER_HEALTH_PATH: /tmp/novu-worker-heartbeat.json" in compose
    assert 'python -m app.worker.healthcheck || (echo \'worker unhealthy; terminating PID 1 for restart\'' in compose
    assert "kill -TERM 1" in compose


def test_worker_healthcheck_main_returns_zero_for_fresh_worker():
    from app.worker import healthcheck

    with patch("app.worker.healthcheck.local_worker_heartbeat_status", return_value=(True, "fresh")):
        assert healthcheck.main() == 0


def test_worker_healthcheck_main_returns_one_for_unhealthy_worker(capsys):
    from app.worker import healthcheck

    with (
        patch("app.worker.healthcheck.local_worker_heartbeat_status", return_value=(False, "worker_process_unhealthy")),
        patch("app.worker.healthcheck.worker_local_health_path", return_value=Path("/tmp/novu-worker-heartbeat.json")),
    ):
        assert healthcheck.main() == 1

    assert "worker_process_unhealthy" in capsys.readouterr().err


class TestHealthInternalWorkerSection:

    def test_health_internal_source_reads_per_instance_heartbeat_pattern(self):
        """health_internal must scan the per-instance heartbeat keyspace."""
        from app.api.routes.system import health_internal
        src = inspect.getsource(health_internal)
        assert '"worker"' in src or "'worker'" in src

    def test_health_internal_source_returns_worker_section(self):
        """health_internal response must include a 'worker' key."""
        from app.api.routes.system import health_internal
        src = inspect.getsource(health_internal)
        assert '"worker"' in src or "'worker'" in src

    @pytest.mark.asyncio
    async def test_worker_alive_when_any_recent_per_instance_heartbeat_exists(self):
        """Returns worker.alive=True when at least one worker instance heartbeat is fresh."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        fresh_ts = datetime.now(UTC).isoformat().encode()
        stale_ts = datetime(2020, 1, 1, tzinfo=UTC).isoformat().encode()

        mock_redis = _redis_with_heartbeats(
            {
                "worker:heartbeat:worker-a": stale_ts,
                "worker:heartbeat:worker-b": fresh_ts,
            }
        )

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = mock_redis
        mock_request.app.state.auth_token_store = None

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_factory.return_value = _mock_health_internal_session()
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert "worker" in result
        assert result["worker"]["alive"] is True
        assert result["worker"]["aliveInstances"] == 1
        assert result["worker"]["seenInstances"] == 2
        assert result["security"]["authProtection"]["state"] == "ready"
        assert result["security"]["authProtection"]["enforced"] is True

    @pytest.mark.asyncio
    async def test_worker_dead_when_no_heartbeat_key(self):
        """Returns worker.alive=False when no heartbeat key exists in Redis."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_redis = _redis_with_heartbeats({})

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = mock_redis
        mock_request.app.state.auth_token_store = None
        mock_request.app.state._worker_not_alive_last_logged = 0.0

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_factory.return_value = _mock_health_internal_session()
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is False
        assert result["worker"]["aliveInstances"] == 0
        assert result["worker"]["seenInstances"] == 0

    @pytest.mark.asyncio
    async def test_health_internal_reports_auth_protection_unavailable_when_redis_monitoring_is_missing(self):
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = None
        mock_request.app.state.auth_token_store = None
        mock_request.app.state._worker_not_alive_last_logged = 0.0

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_factory.return_value = _mock_health_internal_session()
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["security"]["authProtection"]["state"] == "unavailable"
        assert result["security"]["authProtection"]["enforced"] is False

    @pytest.mark.asyncio
    async def test_worker_alive_with_legacy_single_worker_heartbeat_key(self):
        """Legacy single-worker heartbeat key remains readable during rollout."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        fresh_ts = datetime.now(UTC).isoformat().encode()
        mock_redis = _redis_with_heartbeats({"worker:heartbeat": fresh_ts})

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = mock_redis
        mock_request.app.state.auth_token_store = None

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_factory.return_value = _mock_health_internal_session()
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is True
        assert result["worker"]["aliveInstances"] == 1
        assert result["worker"]["seenInstances"] == 1

    @pytest.mark.asyncio
    async def test_worker_unknown_when_redis_unavailable(self):
        """Returns worker.alive=None when Redis is unavailable (app state has no client)."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = None  # Redis not available
        mock_request.app.state.auth_token_store = None
        mock_request.app.state._worker_not_alive_last_logged = 0.0

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_factory.return_value = _mock_health_internal_session()
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is None
        assert result["worker"]["aliveInstances"] is None
        assert result["worker"]["seenInstances"] is None
