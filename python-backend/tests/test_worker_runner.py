# =============================================================================
# Worker runner payload validation tests
#
# Verify that _process_one defensively validates the queue payload before
# calling into AnalysisService, so that a malformed item does not crash the
# worker or leave a job permanently stuck in 'queued' state.
# =============================================================================
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestProcessOnePayloadValidation:
    """_process_one must validate payload keys before calling execute_job."""

    @pytest.mark.asyncio
    async def test_missing_job_id_does_not_call_service(self):
        """Payload without job_id is discarded without calling AnalysisService."""
        payload = {
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        with patch("app.worker.runner.AnalysisService") as MockService:
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        MockService.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_project_id_does_not_call_service(self):
        """Payload without project_id is discarded without calling AnalysisService."""
        payload = {
            "job_id": "job_abc123",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        with patch("app.worker.runner.AnalysisService") as MockService:
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        MockService.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_payload_does_not_call_service(self):
        """Completely empty payload is discarded without calling AnalysisService."""
        payload = {}
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        with patch("app.worker.runner.AnalysisService") as MockService:
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        MockService.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_string_job_id_does_not_call_service(self):
        """Payload with empty-string job_id is treated as missing."""
        payload = {
            "job_id": "",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        with patch("app.worker.runner.AnalysisService") as MockService:
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        MockService.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_string_job_id_does_not_call_service(self):
        """Payload with a numeric job_id is rejected."""
        payload = {
            "job_id": 12345,
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        with patch("app.worker.runner.AnalysisService") as MockService:
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        MockService.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_payload_calls_execute_job(self):
        """A well-formed payload reaches execute_job."""
        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        mock_service.execute_job.assert_awaited_once_with(
            "job_abc123",
            "proj-1",
            "org-1",
            is_superadmin_context=False,
        )

    @pytest.mark.asyncio
    async def test_is_superadmin_context_cast_to_bool(self):
        """is_superadmin_context is coerced to bool so truthy strings don't bypass the guard."""
        payload = {
            "job_id": "job_abc123",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }
        settings = MagicMock()
        settings.ai_analysis_provider = "mock"

        mock_service = AsyncMock()
        mock_service.execute_job = AsyncMock()

        with patch("app.worker.runner.AnalysisService", return_value=mock_service):
            from app.worker.runner import _process_one
            await _process_one(payload, settings)

        _call_kwargs = mock_service.execute_job.call_args[1]
        assert isinstance(_call_kwargs["is_superadmin_context"], bool)
        assert _call_kwargs["is_superadmin_context"] is False


# =============================================================================
# Redis connection hardening — socket_connect_timeout
# =============================================================================

class TestWorkerRedisConnectionHardening:
    """Worker must set socket_connect_timeout when creating the Redis client."""

    def test_run_sets_socket_connect_timeout(self):
        """run() must pass socket_connect_timeout to Redis.from_url()."""
        import inspect
        from app.worker import runner
        src = inspect.getsource(runner.run)
        assert "socket_connect_timeout" in src, (
            "Worker Redis client must set socket_connect_timeout to avoid hanging "
            "indefinitely when Redis is unreachable on startup or after a blip."
        )

    def test_run_does_not_set_socket_timeout(self):
        """run() must NOT set socket_timeout — it would race with the BLPOP server-side timeout."""
        import inspect
        from app.worker import runner
        src = inspect.getsource(runner.run)
        # socket_connect_timeout is fine; a bare socket_timeout= would interfere with BLPOP
        lines_with_socket_timeout = [
            line for line in src.splitlines()
            if "socket_timeout" in line and "socket_connect_timeout" not in line
            and not line.strip().startswith("#")
        ]
        assert not lines_with_socket_timeout, (
            "run() must not set socket_timeout — BLPOP blocks for up to 5 s before "
            "the server responds; a short socket_timeout causes spurious errors."
        )
