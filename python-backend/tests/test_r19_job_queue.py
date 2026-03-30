import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.worker.queue import (
    InvalidAnalysisJobPayloadError,
    QUEUE_KEY,
    dequeue_analysis_job,
    enqueue_analysis_job,
)


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

    @pytest.mark.asyncio
    async def test_rejects_invalid_payload_before_push(self):
        redis = AsyncMock()

        with pytest.raises(InvalidAnalysisJobPayloadError):
            await enqueue_analysis_job(
                redis,
                job_id="   ",
                project_id="proj-2",
                organization_id="org-2",
                is_superadmin_context=False,
            )

        redis.rpush.assert_not_called()


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
    async def test_rejects_malformed_json(self):
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=(QUEUE_KEY.encode(), b"{broken"))

        with pytest.raises(InvalidAnalysisJobPayloadError):
            await dequeue_analysis_job(redis)

    @pytest.mark.asyncio
    async def test_rejects_non_object_json(self):
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=(QUEUE_KEY.encode(), json.dumps(["bad"]).encode()))

        with pytest.raises(InvalidAnalysisJobPayloadError):
            await dequeue_analysis_job(redis)

    @pytest.mark.asyncio
    async def test_rejects_structurally_invalid_object_json(self):
        raw = json.dumps({
            "job_id": "job-3",
            "organization_id": "org-3",
            "is_superadmin_context": False,
        }).encode()
        redis = AsyncMock()
        redis.blpop = AsyncMock(return_value=(QUEUE_KEY.encode(), raw))

        with pytest.raises(InvalidAnalysisJobPayloadError):
            await dequeue_analysis_job(redis)

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


class TestExecuteJobStatusGuard:
    @pytest.mark.asyncio
    async def test_skips_running_job(self):
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
            await service.execute_job("job-1", "proj-1", "org-1", is_superadmin_context=False)

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


class TestCreateAnalysisJobRoute:
    def test_enqueues_when_queue_available(self):
        from app.api.deps import get_job_queue

        mock_redis = AsyncMock()
        mock_request = MagicMock()
        mock_request.app.state.job_queue = mock_redis
        result = get_job_queue(mock_request)
        assert result is mock_redis

    def test_get_job_queue_returns_none_when_not_set(self):
        from app.api.deps import get_job_queue

        mock_request = MagicMock()
        del mock_request.app.state.job_queue
        mock_request.app.state = MagicMock(spec=[])
        result = get_job_queue(mock_request)
        assert result is None
