import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.worker.queue as queue_module
from app.services.analysis_service import AnalysisJobCreateResult
from app.worker.queue import (
    AnalysisJobQueueCapacityExceededError,
    DLQ_KEY_PREFIX,
    InvalidAnalysisJobPayloadError,
    PROCESSING_QUEUE_KEY,
    QUEUE_KEY,
    RETRY_QUEUE_KEY,
    ack_analysis_job,
    dequeue_analysis_job,
    enqueue_analysis_job,
    get_dlq_job,
    get_analysis_job_queue_counts,
    get_expired_analysis_job_leases,
    move_analysis_job_to_dlq,
    promote_scheduled_analysis_jobs,
    requeue_dlq_job,
    requeue_expired_analysis_job,
    schedule_analysis_job_retry,
)


class FakeRedisQueue:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, int]] = {}
        self.sequences: dict[str, int] = {}
        self.values: dict[str, str] = {}

    async def rpush(self, key: str, raw: str) -> int:
        self.lists.setdefault(key, []).append(raw)
        return len(self.lists[key])

    async def llen(self, key: str) -> int:
        return len(self.lists.setdefault(key, []))

    async def eval(self, script: str, numkeys: int, *parts: object):
        keys = [str(part) for part in parts[:numkeys]]
        args = [str(part) for part in parts[numkeys:]]

        if script == queue_module._LEASE_JOB_SCRIPT:
            queue_key, processing_key, expiry_key, lease_prefix, sequence_key = keys
            queue_items = self.lists.setdefault(queue_key, [])
            if not queue_items:
                return None

            raw = queue_items.pop(0)
            token = str(self.sequences.get(sequence_key, 0) + 1)
            self.sequences[sequence_key] = int(token)
            leased_at_ms, worker_id, lease_timeout_ms = args
            expires_at_ms = str(int(leased_at_ms) + int(lease_timeout_ms))

            self.lists.setdefault(processing_key, []).append(raw)
            self.hashes[f"{lease_prefix}{token}"] = {
                "token": token,
                "raw": raw,
                "worker_id": worker_id,
                "leased_at_ms": leased_at_ms,
                "lease_timeout_ms": lease_timeout_ms,
                "expires_at_ms": expires_at_ms,
            }
            self.zsets.setdefault(expiry_key, {})[token] = int(expires_at_ms)
            return [token, raw, worker_id, leased_at_ms, lease_timeout_ms, expires_at_ms]

        if script == queue_module._ACK_JOB_SCRIPT:
            lease_prefix, processing_key, expiry_key = keys
            token, worker_id = args
            lease_key = f"{lease_prefix}{token}"
            lease = self.hashes.get(lease_key)
            if lease is None:
                return 0
            if lease["worker_id"] != worker_id:
                return -1

            raw = lease["raw"]
            processing = self.lists.setdefault(processing_key, [])
            if raw in processing:
                processing.remove(raw)
            self.hashes.pop(lease_key, None)
            self.zsets.setdefault(expiry_key, {}).pop(token, None)
            return 1

        if script == queue_module._ENQUEUE_WITH_LIMIT_SCRIPT:
            queue_key, processing_key = keys
            raw, max_depth = args
            queue_depth = len(self.lists.setdefault(queue_key, []))
            processing_depth = len(self.lists.setdefault(processing_key, []))
            if queue_depth + processing_depth + 1 > int(max_depth):
                return [0, queue_depth, processing_depth]
            self.lists.setdefault(queue_key, []).append(raw)
            return [1, queue_depth + 1, processing_depth]

        if script == queue_module._RENEW_LEASE_SCRIPT:
            lease_prefix, expiry_key = keys
            token, worker_id, leased_at_ms, lease_timeout_ms = args
            lease_key = f"{lease_prefix}{token}"
            lease = self.hashes.get(lease_key)
            if lease is None:
                return 0
            if lease["worker_id"] != worker_id:
                return -1

            expires_at_ms = str(int(leased_at_ms) + int(lease_timeout_ms))
            lease["leased_at_ms"] = leased_at_ms
            lease["lease_timeout_ms"] = lease_timeout_ms
            lease["expires_at_ms"] = expires_at_ms
            self.zsets.setdefault(expiry_key, {})[token] = int(expires_at_ms)
            return 1

        if script == queue_module._SCHEDULE_RETRY_SCRIPT:
            lease_prefix, processing_key, expiry_key, retry_key = keys
            token, worker_id, expected_leased_at_ms, retry_at_ms = args
            lease_key = f"{lease_prefix}{token}"
            lease = self.hashes.get(lease_key)
            if lease is None:
                return 0
            if lease["worker_id"] != worker_id:
                return -1
            if lease["leased_at_ms"] != expected_leased_at_ms:
                return 0

            raw = lease["raw"]
            processing = self.lists.setdefault(processing_key, [])
            if raw in processing:
                processing.remove(raw)
            self.zsets.setdefault(retry_key, {})[raw] = int(retry_at_ms)
            self.hashes.pop(lease_key, None)
            self.zsets.setdefault(expiry_key, {}).pop(token, None)
            return 1

        if script == queue_module._FINALIZE_EXPIRED_LEASE_SCRIPT:
            lease_prefix, processing_key, expiry_key, queue_key = keys
            token, expected_leased_at_ms, action = args
            lease_key = f"{lease_prefix}{token}"
            lease = self.hashes.get(lease_key)
            if lease is None:
                return 0
            if lease["leased_at_ms"] != expected_leased_at_ms:
                return 0

            raw = lease["raw"]
            processing = self.lists.setdefault(processing_key, [])
            if raw in processing:
                processing.remove(raw)
            if action == "requeue":
                self.lists.setdefault(queue_key, []).append(raw)
            self.hashes.pop(lease_key, None)
            self.zsets.setdefault(expiry_key, {}).pop(token, None)
            return 1

        if script == queue_module._MOVE_TO_DLQ_SCRIPT:
            lease_prefix, processing_key, expiry_key, dlq_key = keys
            token, worker_id, expected_leased_at_ms, dlq_payload = args
            lease_key = f"{lease_prefix}{token}"
            lease = self.hashes.get(lease_key)
            if lease is None:
                return 0
            if lease["worker_id"] != worker_id:
                return -1
            if lease["leased_at_ms"] != expected_leased_at_ms:
                return 0

            raw = lease["raw"]
            processing = self.lists.setdefault(processing_key, [])
            if raw in processing:
                processing.remove(raw)
            self.values[dlq_key] = dlq_payload
            self.hashes.pop(lease_key, None)
            self.zsets.setdefault(expiry_key, {}).pop(token, None)
            return 1

        if script == queue_module._PROMOTE_RETRY_SCRIPT:
            queue_key, retry_key = keys
            now_ms, limit = args
            due = [
                raw
                for raw, score in sorted(self.zsets.setdefault(retry_key, {}).items(), key=lambda item: item[1])
                if score <= int(now_ms)
            ][:int(limit)]
            moved = 0
            for raw in due:
                if raw in self.zsets.setdefault(retry_key, {}):
                    self.zsets[retry_key].pop(raw, None)
                    self.lists.setdefault(queue_key, []).append(raw)
                    moved += 1
            return moved

        raise AssertionError(f"Unexpected script: {script[:40]!r}")

    async def zrangebyscore(self, key: str, *, min: int, max: int, start: int = 0, num: int = 100):
        tokens = [
            token
            for token, expiry in sorted(self.zsets.setdefault(key, {}).items(), key=lambda item: item[1])
            if min <= expiry <= max
        ]
        return tokens[start:start + num]

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return 1 if self.values.pop(key, None) is not None else 0


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

    @pytest.mark.asyncio
    async def test_rejects_enqueue_when_queue_capacity_would_be_exceeded(self):
        redis = FakeRedisQueue()

        await enqueue_analysis_job(
            redis,
            job_id="job-1",
            project_id="proj-1",
            organization_id="org-1",
            is_superadmin_context=False,
            max_depth=1,
        )

        with pytest.raises(AnalysisJobQueueCapacityExceededError):
            await enqueue_analysis_job(
                redis,
                job_id="job-2",
                project_id="proj-2",
                organization_id="org-2",
                is_superadmin_context=False,
                max_depth=1,
            )

    @pytest.mark.asyncio
    async def test_queue_count_includes_queued_and_processing(self):
        redis = FakeRedisQueue()

        await enqueue_analysis_job(
            redis,
            job_id="job-queued",
            project_id="proj-queued",
            organization_id="org-1",
            is_superadmin_context=False,
        )
        await enqueue_analysis_job(
            redis,
            job_id="job-processing",
            project_id="proj-processing",
            organization_id="org-1",
            is_superadmin_context=False,
        )
        await dequeue_analysis_job(redis, worker_id="worker-a", lease_timeout_seconds=600)

        queued, processing = await get_analysis_job_queue_counts(redis)

        assert queued == 1
        assert processing == 1


class TestLeasedQueueFlow:
    @pytest.mark.asyncio
    async def test_dequeue_returns_leased_payload_and_moves_item_to_processing(self):
        redis = FakeRedisQueue()
        now = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

        await enqueue_analysis_job(
            redis,
            job_id="job-3",
            project_id="proj-3",
            organization_id="org-3",
            is_superadmin_context=False,
        )

        lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
            now=now,
        )

        assert lease is not None
        assert lease.payload == {
            "job_id": "job-3",
            "project_id": "proj-3",
            "organization_id": "org-3",
            "is_superadmin_context": False,
        }
        assert lease.worker_id == "worker-a"
        assert lease.lease_timeout_seconds == 600
        assert redis.lists[QUEUE_KEY] == []
        assert len(redis.lists[PROCESSING_QUEUE_KEY]) == 1

    @pytest.mark.asyncio
    async def test_returns_none_when_queue_is_empty(self):
        redis = FakeRedisQueue()
        result = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_ack_removes_processing_item_and_lease_metadata(self):
        redis = FakeRedisQueue()

        await enqueue_analysis_job(
            redis,
            job_id="job-4",
            project_id="proj-4",
            organization_id="org-4",
            is_superadmin_context=False,
        )
        lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
        )
        assert lease is not None

        acked = await ack_analysis_job(redis, lease)

        assert acked is True
        assert redis.lists[PROCESSING_QUEUE_KEY] == []
        assert redis.hashes == {}

    @pytest.mark.asyncio
    async def test_lease_expiration_exposes_job_to_reaper(self):
        redis = FakeRedisQueue()
        leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

        await enqueue_analysis_job(
            redis,
            job_id="job-5",
            project_id="proj-5",
            organization_id="org-5",
            is_superadmin_context=False,
        )
        lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
            now=leased_at,
        )
        assert lease is not None

        before_expiry = await get_expired_analysis_job_leases(
            redis,
            now=leased_at + timedelta(minutes=9),
        )
        after_expiry = await get_expired_analysis_job_leases(
            redis,
            now=leased_at + timedelta(minutes=11),
        )

        assert before_expiry == []
        assert [item.job_id for item in after_expiry] == ["job-5"]

    @pytest.mark.asyncio
    async def test_requeue_expired_lease_recovers_lost_job(self):
        redis = FakeRedisQueue()
        leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

        await enqueue_analysis_job(
            redis,
            job_id="job-6",
            project_id="proj-6",
            organization_id="org-6",
            is_superadmin_context=False,
        )
        first_lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
            now=leased_at,
        )
        assert first_lease is not None

        expired = await get_expired_analysis_job_leases(
            redis,
            now=leased_at + timedelta(minutes=11),
        )
        assert len(expired) == 1

        requeued = await requeue_expired_analysis_job(redis, expired[0])
        recovered_lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-b",
            lease_timeout_seconds=600,
            now=leased_at + timedelta(minutes=11, seconds=1),
        )

        assert requeued is True
        assert recovered_lease is not None
        assert recovered_lease.job_id == "job-6"
        assert recovered_lease.worker_id == "worker-b"


class TestRetryAndDlqFlow:
    @pytest.mark.asyncio
    async def test_schedule_retry_moves_lease_out_of_processing_and_promotes_later(self):
        redis = FakeRedisQueue()
        leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)
        retry_at = leased_at + timedelta(seconds=30)

        await enqueue_analysis_job(
            redis,
            job_id="job-retry",
            project_id="proj-retry",
            organization_id="org-1",
            is_superadmin_context=False,
        )
        lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
            now=leased_at,
        )
        assert lease is not None

        scheduled = await schedule_analysis_job_retry(
            redis,
            lease,
            retry_at=retry_at,
        )

        assert scheduled is True
        assert redis.lists[PROCESSING_QUEUE_KEY] == []
        assert lease.raw_payload in redis.zsets[RETRY_QUEUE_KEY]

        moved_before_due = await promote_scheduled_analysis_jobs(
            redis,
            now=leased_at + timedelta(seconds=10),
        )
        moved_after_due = await promote_scheduled_analysis_jobs(
            redis,
            now=retry_at + timedelta(seconds=1),
        )

        assert moved_before_due == 0
        assert moved_after_due == 1
        assert len(redis.lists[QUEUE_KEY]) == 1

    @pytest.mark.asyncio
    async def test_move_to_dlq_and_requeue_by_job_id(self):
        redis = FakeRedisQueue()
        leased_at = datetime(2026, 3, 30, 12, 0, tzinfo=UTC)

        await enqueue_analysis_job(
            redis,
            job_id="job-dlq",
            project_id="proj-dlq",
            organization_id="org-1",
            is_superadmin_context=False,
        )
        lease = await dequeue_analysis_job(
            redis,
            worker_id="worker-a",
            lease_timeout_seconds=600,
            now=leased_at,
        )
        assert lease is not None

        moved = await move_analysis_job_to_dlq(
            redis,
            lease,
            attempt_count=3,
            reason="provider failed repeatedly",
            now=leased_at,
        )

        assert moved is True
        assert redis.lists[PROCESSING_QUEUE_KEY] == []
        assert f"{DLQ_KEY_PREFIX}{lease.job_id}" in redis.values

        dlq_payload = await get_dlq_job(redis, lease.job_id)
        assert dlq_payload is not None
        assert dlq_payload["attempt_count"] == 3
        assert dlq_payload["reason"] == "provider failed repeatedly"

        requeued = await requeue_dlq_job(
            redis,
            job_id=lease.job_id,
            max_depth=10,
        )

        assert requeued is not None
        assert len(redis.lists[QUEUE_KEY]) == 1
        assert f"{DLQ_KEY_PREFIX}{lease.job_id}" not in redis.values


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


class TestDuplicateEnqueueGuard:
    @pytest.mark.asyncio
    async def test_create_analysis_job_skips_enqueue_for_existing_active_job(self):
        from app.api.routes.analysis_jobs import create_analysis_job

        current_user = MagicMock()
        current_user.id = "usr-1"
        current_user.isSuperAdmin = False
        current_user.organizationId = "org-1"

        project = MagicMock(id="proj-1")
        existing_job = MagicMock(id="job-existing", status="queued")
        project_service = MagicMock(get_project=AsyncMock(return_value=project))
        analysis_service = MagicMock(
            provider_key="mock",
            create_job=AsyncMock(
                return_value=AnalysisJobCreateResult(job=existing_job, created_new=False)
            ),
        )
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

        with patch("app.api.routes.analysis_jobs.enqueue_analysis_job", new=AsyncMock()) as enqueue_mock:
            response = await create_analysis_job(
                case_id="proj-1",
                request=request,
                current_user=current_user,
                project_service=project_service,
                analysis_service=analysis_service,
                job_queue=AsyncMock(),
            )

        enqueue_mock.assert_not_awaited()
        assert response.jobId == "job-existing"
        assert response.workTypeCode is None
        assert response.analysisProfileCode is None
        assert response.analysisProfileVersion is None


class TestQueueOverflowGuards:
    @pytest.mark.asyncio
    async def test_create_analysis_job_returns_429_when_enqueue_race_hits_capacity(self):
        from app.api.routes.analysis_jobs import create_analysis_job

        current_user = MagicMock()
        current_user.id = "usr-1"
        current_user.isSuperAdmin = False
        current_user.organizationId = "org-1"

        project = MagicMock(id="proj-1")
        new_job = MagicMock(id="job-new", status="queued")
        project_service = MagicMock(get_project=AsyncMock(return_value=project))
        analysis_service = MagicMock(
            provider_key="mock",
            create_job=AsyncMock(
                return_value=AnalysisJobCreateResult(job=new_job, created_new=True)
            ),
            cancel_analysis_job=AsyncMock(),
        )
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

        with (
            patch("app.api.routes.analysis_jobs.get_settings") as get_settings,
            patch(
                "app.api.routes.analysis_jobs.enqueue_analysis_job",
                new=AsyncMock(
                    side_effect=AnalysisJobQueueCapacityExceededError(
                        queued=1000,
                        processing=0,
                        max_depth=1000,
                    )
                ),
            ),
        ):
            get_settings.return_value.analysis_queue_max_depth = 1000
            with pytest.raises(HTTPException) as exc_info:
                await create_analysis_job(
                    case_id="proj-1",
                    request=request,
                    current_user=current_user,
                    project_service=project_service,
                    analysis_service=analysis_service,
                    job_queue=AsyncMock(),
                )

        assert exc_info.value.status_code == 429
        analysis_service.cancel_analysis_job.assert_awaited_once_with("job-new", organization_id="org-1")

    @pytest.mark.asyncio
    async def test_retry_analysis_job_returns_429_when_enqueue_race_hits_capacity(self):
        from app.api.routes.analysis_jobs import retry_analysis_job

        current_user = MagicMock()
        current_user.id = "usr-1"
        current_user.isSuperAdmin = False
        current_user.organizationId = "org-1"

        analysis_service = MagicMock(
            provider_key="mock",
            get_job=AsyncMock(return_value={"id": "job-old"}),
            retry_job=AsyncMock(return_value=MagicMock(id="job-new", project_id="proj-1", status="queued")),
            cancel_analysis_job=AsyncMock(),
        )
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})

        with (
            patch("app.api.routes.analysis_jobs.get_settings") as get_settings,
            patch(
                "app.api.routes.analysis_jobs.enqueue_analysis_job",
                new=AsyncMock(
                    side_effect=AnalysisJobQueueCapacityExceededError(
                        queued=999,
                        processing=1,
                        max_depth=1000,
                    )
                ),
            ),
        ):
            get_settings.return_value.analysis_queue_max_depth = 1000
            with pytest.raises(HTTPException) as exc_info:
                await retry_analysis_job(
                    job_id="job-old",
                    request=request,
                    current_user=current_user,
                    analysis_service=analysis_service,
                    project_service=MagicMock(),
                    job_queue=AsyncMock(),
                )

        assert exc_info.value.status_code == 429
        analysis_service.cancel_analysis_job.assert_awaited_once_with("job-new", organization_id="org-1")
