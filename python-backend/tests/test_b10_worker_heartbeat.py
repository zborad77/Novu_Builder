"""B10: Worker heartbeat detection tests.

Coverage:
1. Worker runner writes heartbeat key to Redis in the main loop
2. /health/internal reports worker alive when heartbeat is fresh
3. /health/internal reports worker dead when heartbeat is missing
4. /health/internal reports worker status unknown when Redis is unavailable
"""
import inspect
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 1. Worker runner writes heartbeat ────────────────────────────────────────

class TestWorkerHeartbeat:

    def test_runner_heartbeat_key_constant_value(self):
        """_HEARTBEAT_KEY must equal 'worker:heartbeat' (checked by health endpoint)."""
        from app.worker import runner
        assert runner._HEARTBEAT_KEY == "worker:heartbeat", (
            "_HEARTBEAT_KEY must be 'worker:heartbeat' — health endpoint expects this exact key"
        )

    def test_runner_source_references_heartbeat_key(self):
        """runner.run() must reference _HEARTBEAT_KEY (i.e. actually write the heartbeat)."""
        from app.worker import runner
        src = inspect.getsource(runner.run)
        assert "_HEARTBEAT_KEY" in src, (
            "run() must use _HEARTBEAT_KEY to write the heartbeat"
        )

    def test_runner_source_sets_ttl_on_heartbeat(self):
        """Heartbeat must be written with an expiry (ex=...) so stale keys auto-expire."""
        from app.worker import runner
        src = inspect.getsource(runner.run)
        assert "ex=" in src, (
            "redis.set() for heartbeat must include ex= TTL argument"
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

class TestHealthInternalWorkerSection:

    def test_health_internal_source_reads_heartbeat_key(self):
        """health_internal must read 'worker:heartbeat' from Redis."""
        from app.api.routes.system import health_internal
        src = inspect.getsource(health_internal)
        assert "worker:heartbeat" in src

    def test_health_internal_source_returns_worker_section(self):
        """health_internal response must include a 'worker' key."""
        from app.api.routes.system import health_internal
        src = inspect.getsource(health_internal)
        assert '"worker"' in src or "'worker'" in src

    @pytest.mark.asyncio
    async def test_worker_alive_when_recent_heartbeat(self):
        """Returns worker.alive=True when heartbeat timestamp is within 90 s."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        fresh_ts = datetime.now(UTC).isoformat().encode()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=fresh_ts)

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

            result = await health_internal(
                request=mock_request,
                _=mock_current_user,
            )

        assert "worker" in result
        assert result["worker"]["alive"] is True

    @pytest.mark.asyncio
    async def test_worker_dead_when_no_heartbeat_key(self):
        """Returns worker.alive=False when no heartbeat key in Redis."""
        from app.api.routes.system import health_internal
        from app.schemas.auth import AuthUserRead

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

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

            result = await health_internal(
                request=mock_request,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is False

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

            result = await health_internal(
                request=mock_request,
                _=mock_current_user,
            )

        assert result["worker"]["alive"] is None
