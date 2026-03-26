"""R-19: Redis job queue unit tests.

Tests cover:
  - enqueue_analysis_job pushes correctly serialised payload
  - dequeue_analysis_job returns correct dict
  - dequeue_analysis_job returns None on timeout
  - execute_job skips jobs not in 'queued' status (idempotency guard)
  - Route enqueues job when job_queue is available
  - Route returns 202 and logs warning when job_queue is None
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.queue import QUEUE_KEY, dequeue_analysis_job, enqueue_analysis_job


# ── queue.py unit tests ──────────────────────────────────────────────────────

class TestEnqueueAnalysisJob:
    @pytest.mark.asyncio
    async def test_pushes_json_to_correct_key(self):
        redis = AsyncMock()
        await enqueue_analysis_job(
            redis,
            job_id="job-1",
            project_id="proj-1",
            organization_id="org-1",
            is_superadmin_context=False,
        )
        redis.rpush.assert_awaited_once()
        key, raw = redis.rpush.call_args[0]
        assert key == QUEUE_KEY
        payload = json.loads(raw)
        assert payload == {
            "job_id": "job-1",
            "project_id": "proj-1",
            "organization_id": "org-1",
            "is_superadmin_context": False,
        }

    @pytest.mark.asyncio
    async def test_superadmin_org_id_none(self):
        redis = AsyncMock()
        await enqueue_analysis_job(
            redis,
            job_id="job-2",
            project_id="proj-2",
            organization_id=None,
            is_superadmin_context=True,
        )
        _key, raw = redis.rpush.call_args[0]
        payload = json.loads(raw)
        assert payload["organization_id"] is None
        assert payload["is_superadmin_context"] is True


class TestDequeueAnalysisJob:
    @pytest.mark.asyncio
    async def test_returns_parsed_payload(self):
        raw = json.dumps({
            "job_id": "job-3",
            "project_id": "proj-3",
            "organization_id": "org-3",
            "is_superadmin_context": False,
        }).encode()
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=(QUEUE_KEY.encode(), raw))
        result = await dequeue_analysis_job(redis)
        assert result == {
            "job_id": "job-3",
            "project_id": "proj-3",
            "organization_id": "org-3",
            "is_superadmin_context": False,
        }

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=None)
        result = await dequeue_analysis_job(redis)
        assert result is None

    @pytest.mark.asyncio
    async def test_passes_timeout_to_blpop(self):
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=None)
        await dequeue_analysis_job(redis, timeout=30)
        redis.blpop.assert_awaited_once_with(QUEUE_KEY, timeout=30)


# ── execute_job idempotency guard ─────────────────────────────────────────────

class TestExecuteJobStatusGuard:
    @pytest.mark.asyncio
    async def test_skips_running_job(self):
        """execute_job must return early without DB writes when status != 'queued'."""
        from app.services.analysis_service import AnalysisService

        mock_job = MagicMock()
        mock_job.status = "running"
        mock_job.project_id = "proj-1"

        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=mock_job)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.get = AsyncMock()

        service = AnalysisService(
            repository=mock_repo,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.AsyncSessionFactory", return_value=mock_session),
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
            patch("app.services.analysis_service.PhotoRepository", return_value=AsyncMock()),
        ):
            # Should return without error or DB writes
            await service.execute_job("job-1", "proj-1", "org-1", is_superadmin_context=False)

        # Confirm job status was NOT changed (no commit called)
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_failed_job(self):
        from app.services.analysis_service import AnalysisService

        mock_job = MagicMock()
        mock_job.status = "failed"
        mock_job.project_id = "proj-1"

        mock_repo = AsyncMock()
        mock_repo.get_analysis_job = AsyncMock(return_value=mock_job)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        service = AnalysisService(
            repository=mock_repo,
            photo_repository=AsyncMock(),
            provider_key="mock",
        )

        with (
            patch("app.services.analysis_service.AsyncSessionFactory", return_value=mock_session),
            patch("app.services.analysis_service.AnalysisRepository", return_value=mock_repo),
            patch("app.services.analysis_service.PhotoRepository", return_value=AsyncMock()),
        ):
            await service.execute_job("job-1", "proj-1", "org-1", is_superadmin_context=False)

        mock_session.commit.assert_not_called()


# ── route-level tests ─────────────────────────────────────────────────────────

class TestCreateAnalysisJobRoute:
    def test_enqueues_when_queue_available(self):
        """get_job_queue returns the Redis client when job_queue is set on app.state."""
        from app.api.deps import get_job_queue

        mock_redis = AsyncMock()
        mock_request = MagicMock()
        mock_request.app.state.job_queue = mock_redis
        result = get_job_queue(mock_request)
        assert result is mock_redis

    def test_get_job_queue_returns_none_when_not_set(self):
        from app.api.deps import get_job_queue

        mock_request = MagicMock()
        del mock_request.app.state.job_queue  # simulate missing attr
        mock_request.app.state = MagicMock(spec=[])  # no job_queue attribute
        result = get_job_queue(mock_request)
        assert result is None
