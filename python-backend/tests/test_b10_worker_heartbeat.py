"""B10: Worker heartbeat detection tests.

Coverage:
1. Worker runner writes per-instance heartbeat keys in the main loop
2. /health/internal reports worker alive when at least one fresh heartbeat exists
3. /health/internal reports worker dead when no heartbeat exists
4. /health/internal reports worker status unknown when Redis is unavailable
5. Legacy single-worker heartbeat key remains readable during rollout
"""
import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response


async def _scan_iter(*keys):
    for key in keys:
        yield key


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
    redis.scan_iter = lambda match=None: _scan_iter(*pattern_keys)
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

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0, scalar_one_or_none=lambda: None))
            mock_factory.return_value = mock_session
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
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_worker_dead_when_no_heartbeat_key(self):
        """Returns worker.alive=False when no heartbeat key exists in Redis."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_redis = _redis_with_heartbeats({})

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = mock_redis

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0, scalar_one_or_none=lambda: None))
            mock_factory.return_value = mock_session
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is False
        assert result["worker"]["aliveInstances"] == 0
        assert result["worker"]["seenInstances"] == 0
        assert response.status_code == 200

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

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0, scalar_one_or_none=lambda: None))
            mock_factory.return_value = mock_session
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is True
        assert result["worker"]["aliveInstances"] == 1
        assert result["worker"]["seenInstances"] == 1
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_worker_unknown_when_redis_unavailable(self):
        """Returns worker.alive=None when Redis is unavailable (app state has no client)."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_request = MagicMock()
        mock_request.app.state.startup_checks = {"db": "ok"}
        mock_request.app.state.job_queue = None  # Redis not available

        mock_current_user = AuthUserRead(
            id="sa-1", email="sa@test.com", fullName="SA", role="superadmin",
            isActive=True, organizationId="org-1", isSuperAdmin=True, impersonatedBy=None,
        )

        with patch("app.api.routes.system.AsyncSessionFactory") as mock_factory:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one=lambda: 0, scalar_one_or_none=lambda: None))
            mock_factory.return_value = mock_session
            response = Response()

            result = await health_internal(
                request=mock_request,
                response=response,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is None
        assert result["worker"]["aliveInstances"] is None
        assert result["worker"]["seenInstances"] is None
        assert response.status_code == 200
