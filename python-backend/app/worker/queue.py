"""Reliable Redis-backed analysis job queue with lease/ack semantics.

Producer contract:
    enqueue_analysis_job() validates the JSON payload and appends it to the
    durable queue list.

Worker contract:
    dequeue_analysis_job() atomically moves the next queue item into the
    processing list and creates a lease record. Successful processing must ACK
    the lease; crashed workers leave the lease behind and the reaper can safely
    requeue it after the visibility timeout expires.

Redis transport contract:
    Queue functions operate against a Redis-like client that may be backed by a
    failover-aware wrapper. Read operations may transparently switch to another
    candidate endpoint, but mutating operations must never be replayed
    implicitly after a transport error because lease/enqueue truthfulness takes
    priority over "hidden HA".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from redis.asyncio import Redis

QUEUE_KEY = "analysis:jobs"
PROCESSING_QUEUE_KEY = "analysis:processing"
RETRY_QUEUE_KEY = "analysis:retry"
LEASE_KEY_PREFIX = "analysis:lease:"
LEASE_EXPIRY_ZSET_KEY = "analysis:lease_expiry"
LEASE_SEQUENCE_KEY = "analysis:lease_sequence"
DLQ_KEY_PREFIX = "analysis:dlq:"

_LEASE_JOB_SCRIPT = """
local raw = redis.call('LPOP', KEYS[1])
if not raw then
    return nil
end

local token = tostring(redis.call('INCR', KEYS[5]))
local lease_key = KEYS[4] .. token
local leased_at_ms = ARGV[1]
local worker_id = ARGV[2]
local lease_timeout_ms = ARGV[3]
local expires_at_ms = tostring(tonumber(leased_at_ms) + tonumber(lease_timeout_ms))

redis.call('RPUSH', KEYS[2], raw)
redis.call(
    'HSET',
    lease_key,
    'token', token,
    'raw', raw,
    'worker_id', worker_id,
    'leased_at_ms', leased_at_ms,
    'lease_timeout_ms', lease_timeout_ms,
    'expires_at_ms', expires_at_ms
)
redis.call('ZADD', KEYS[3], expires_at_ms, token)
return {token, raw, worker_id, leased_at_ms, lease_timeout_ms, expires_at_ms}
"""

_ENQUEUE_WITH_LIMIT_SCRIPT = """
local queue_depth = redis.call('LLEN', KEYS[1])
local processing_depth = redis.call('LLEN', KEYS[2])
local max_depth = tonumber(ARGV[2])
if (queue_depth + processing_depth + 1) > max_depth then
    return {0, queue_depth, processing_depth}
end

redis.call('RPUSH', KEYS[1], ARGV[1])
return {1, queue_depth + 1, processing_depth}
"""

_ACK_JOB_SCRIPT = """
local token = ARGV[1]
local worker_id = ARGV[2]
local lease_key = KEYS[1] .. token
if redis.call('EXISTS', lease_key) == 0 then
    return 0
end

local owner = redis.call('HGET', lease_key, 'worker_id')
if owner ~= worker_id then
    return -1
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    redis.call('LREM', KEYS[2], 1, raw)
end
redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], token)
return 1
"""

_RENEW_LEASE_SCRIPT = """
local token = ARGV[1]
local worker_id = ARGV[2]
local leased_at_ms = ARGV[3]
local lease_timeout_ms = ARGV[4]
local lease_key = KEYS[1] .. token
if redis.call('EXISTS', lease_key) == 0 then
    return 0
end

local owner = redis.call('HGET', lease_key, 'worker_id')
if owner ~= worker_id then
    return -1
end

local expires_at_ms = tostring(tonumber(leased_at_ms) + tonumber(lease_timeout_ms))
redis.call(
    'HSET',
    lease_key,
    'leased_at_ms', leased_at_ms,
    'lease_timeout_ms', lease_timeout_ms,
    'expires_at_ms', expires_at_ms
)
redis.call('ZADD', KEYS[2], expires_at_ms, token)
return 1
"""

_SCHEDULE_RETRY_SCRIPT = """
local lease_key = KEYS[1] .. ARGV[1]
if redis.call('EXISTS', lease_key) == 0 then
    return 0
end

local owner = redis.call('HGET', lease_key, 'worker_id')
if owner ~= ARGV[2] then
    return -1
end

local actual_leased_at_ms = redis.call('HGET', lease_key, 'leased_at_ms')
if actual_leased_at_ms ~= ARGV[3] then
    return 0
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    redis.call('LREM', KEYS[2], 1, raw)
    redis.call('ZADD', KEYS[4], ARGV[4], raw)
end
redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""

_FINALIZE_EXPIRED_LEASE_SCRIPT = """
local token = ARGV[1]
local expected_leased_at_ms = ARGV[2]
local action = ARGV[3]
local lease_key = KEYS[1] .. token
if redis.call('EXISTS', lease_key) == 0 then
    return 0
end

local actual_leased_at_ms = redis.call('HGET', lease_key, 'leased_at_ms')
if actual_leased_at_ms ~= expected_leased_at_ms then
    return 0
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    redis.call('LREM', KEYS[2], 1, raw)
    if action == 'requeue' then
        redis.call('RPUSH', KEYS[4], raw)
    end
end

redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], token)
return 1
"""

_MOVE_TO_DLQ_SCRIPT = """
local lease_key = KEYS[1] .. ARGV[1]
if redis.call('EXISTS', lease_key) == 0 then
    return 0
end

local owner = redis.call('HGET', lease_key, 'worker_id')
if owner ~= ARGV[2] then
    return -1
end

local actual_leased_at_ms = redis.call('HGET', lease_key, 'leased_at_ms')
if actual_leased_at_ms ~= ARGV[3] then
    return 0
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    redis.call('LREM', KEYS[2], 1, raw)
end
redis.call('SET', KEYS[4], ARGV[4])
redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""

_PROMOTE_RETRY_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[2], 0, ARGV[1], 'LIMIT', 0, ARGV[2])
local moved = 0
for _, raw in ipairs(due) do
    if redis.call('ZREM', KEYS[2], raw) == 1 then
        redis.call('RPUSH', KEYS[1], raw)
        moved = moved + 1
    end
end
return moved
"""


class InvalidAnalysisJobPayloadError(ValueError):
    """Raised when a Redis queue item cannot be decoded into the expected payload."""


class LostAnalysisJobLeaseError(RuntimeError):
    """Raised when a worker attempts to ACK/renew a lease it no longer owns."""


class AnalysisJobQueueCapacityExceededError(RuntimeError):
    """Raised when enqueue would push the analysis queue beyond the configured cap."""

    def __init__(self, *, queued: int, processing: int, max_depth: int) -> None:
        total = queued + processing
        super().__init__(
            f"Analysis queue is full ({total}/{max_depth}; queued={queued}, processing={processing})."
        )
        self.queued = queued
        self.processing = processing
        self.max_depth = max_depth


def _build_dlq_key(job_id: str) -> str:
    return f"{DLQ_KEY_PREFIX}{job_id}"


class AnalysisJobQueuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    project_id: str
    organization_id: str | None = None
    is_superadmin_context: bool = False

    @field_validator("job_id", "project_id")
    @classmethod
    def _validate_required_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must be a non-empty string")
        return normalized

    @field_validator("organization_id")
    @classmethod
    def _validate_organization_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must be a non-empty string when provided")
        return normalized

    @model_validator(mode="after")
    def _validate_tenant_context(self) -> "AnalysisJobQueuePayload":
        if self.organization_id is None and not self.is_superadmin_context:
            raise ValueError(
                "organization_id is required for non-superadmin worker payloads"
            )
        return self


@dataclass(frozen=True)
class LeasedAnalysisJob:
    token: str
    payload: dict
    raw_payload: str
    worker_id: str
    leased_at_ms: int
    lease_timeout_ms: int
    expires_at_ms: int

    @property
    def job_id(self) -> str:
        return str(self.payload["job_id"])

    @property
    def project_id(self) -> str:
        return str(self.payload["project_id"])

    @property
    def organization_id(self) -> str | None:
        value = self.payload.get("organization_id")
        return None if value is None else str(value)

    @property
    def lease_timeout_seconds(self) -> int:
        return max(1, self.lease_timeout_ms // 1000)


def _utc_now_ms(now: datetime | None = None) -> int:
    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return int(current.timestamp() * 1000)


def _decode_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_raw_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidAnalysisJobPayloadError(
            "Invalid analysis job queue payload: malformed JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidAnalysisJobPayloadError(
            "Invalid analysis job queue payload: expected a JSON object."
        )
    return validate_analysis_job_payload(payload).model_dump()


def _serialize_dlq_payload(
    lease: "LeasedAnalysisJob",
    *,
    attempt_count: int,
    reason: str | None = None,
    now: datetime | None = None,
) -> str:
    payload = {
        "job_id": lease.job_id,
        "project_id": lease.project_id,
        "organization_id": lease.organization_id,
        "is_superadmin_context": bool(lease.payload.get("is_superadmin_context", False)),
        "raw_payload": lease.raw_payload,
        "attempt_count": max(0, int(attempt_count)),
        "reason": reason,
        "moved_at_ms": _utc_now_ms(now),
    }
    return json.dumps(payload)


def _parse_dlq_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidAnalysisJobPayloadError(
            "Invalid analysis job DLQ payload: malformed JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidAnalysisJobPayloadError(
            "Invalid analysis job DLQ payload: expected a JSON object."
        )

    raw_payload = payload.get("raw_payload")
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        raise InvalidAnalysisJobPayloadError(
            "Invalid analysis job DLQ payload: missing raw_payload."
        )

    _parse_raw_payload(raw_payload)
    return payload


async def _enqueue_raw_payload(
    redis: Redis,
    raw_payload: str,
    *,
    max_depth: int | None = None,
) -> None:
    if max_depth is None:
        await redis.rpush(QUEUE_KEY, raw_payload)
        return

    result = await redis.eval(
        _ENQUEUE_WITH_LIMIT_SCRIPT,
        2,
        QUEUE_KEY,
        PROCESSING_QUEUE_KEY,
        raw_payload,
        str(max(1, int(max_depth))),
    )
    if (
        not isinstance(result, (list, tuple))
        or len(result) != 3
        or int(_decode_text(result[0])) != 1
    ):
        queued = int(_decode_text(result[1])) if isinstance(result, (list, tuple)) and len(result) > 1 else 0
        processing = int(_decode_text(result[2])) if isinstance(result, (list, tuple)) and len(result) > 2 else 0
        raise AnalysisJobQueueCapacityExceededError(
            queued=queued,
            processing=processing,
            max_depth=max(1, int(max_depth)),
        )


def validate_analysis_job_payload(payload: object) -> AnalysisJobQueuePayload:
    try:
        return AnalysisJobQueuePayload.model_validate(payload)
    except ValidationError as exc:
        issues: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ())) or "payload"
            issue_message = str(error.get("msg", error.get("type", "invalid")))
            issues.append(f"{location}:{issue_message}")
        summary = "; ".join(issues) if issues else "invalid_payload"
        raise InvalidAnalysisJobPayloadError(summary) from exc


def _leased_job_from_redis_result(result: object) -> LeasedAnalysisJob:
    if not isinstance(result, (list, tuple)) or len(result) != 6:
        raise InvalidAnalysisJobPayloadError("Invalid analysis job lease result from Redis.")

    token = _decode_text(result[0])
    raw_payload = _decode_text(result[1])
    worker_id = _decode_text(result[2])
    leased_at_ms = int(_decode_text(result[3]))
    lease_timeout_ms = int(_decode_text(result[4]))
    expires_at_ms = int(_decode_text(result[5]))
    payload = _parse_raw_payload(raw_payload)
    return LeasedAnalysisJob(
        token=token,
        payload=payload,
        raw_payload=raw_payload,
        worker_id=worker_id,
        leased_at_ms=leased_at_ms,
        lease_timeout_ms=lease_timeout_ms,
        expires_at_ms=expires_at_ms,
    )


async def enqueue_analysis_job(
    redis: Redis,
    *,
    job_id: str,
    project_id: str,
    organization_id: str | None,
    is_superadmin_context: bool,
    max_depth: int | None = None,
) -> None:
    """Push a validated job payload to the tail of the durable Redis queue."""
    payload = validate_analysis_job_payload(
        {
            "job_id": job_id,
            "project_id": project_id,
            "organization_id": organization_id,
            "is_superadmin_context": is_superadmin_context,
        }
    )
    await _enqueue_raw_payload(
        redis,
        json.dumps(payload.model_dump()),
        max_depth=max_depth,
    )


async def get_analysis_job_queue_counts(redis: Redis) -> tuple[int, int]:
    """Return the current durable queue and in-processing depths."""
    if redis is None:
        return 0, 0
    queued = int(await redis.llen(QUEUE_KEY))
    processing = int(await redis.llen(PROCESSING_QUEUE_KEY))
    return queued, processing


async def dequeue_analysis_job(
    redis: Redis,
    *,
    worker_id: str,
    lease_timeout_seconds: int,
    now: datetime | None = None,
) -> LeasedAnalysisJob | None:
    """Lease the next queued job, or return None when the queue is empty."""
    lease_timeout_ms = max(1, int(lease_timeout_seconds)) * 1000
    result = await redis.eval(
        _LEASE_JOB_SCRIPT,
        5,
        QUEUE_KEY,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        LEASE_KEY_PREFIX,
        LEASE_SEQUENCE_KEY,
        str(_utc_now_ms(now)),
        worker_id,
        str(lease_timeout_ms),
    )
    if result is None:
        return None
    return _leased_job_from_redis_result(result)


async def ack_analysis_job(redis: Redis, lease: LeasedAnalysisJob) -> bool:
    """ACK a successfully handled job and remove it from processing."""
    result = await redis.eval(
        _ACK_JOB_SCRIPT,
        3,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        lease.token,
        lease.worker_id,
    )
    if int(result) == -1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    return int(result) == 1


async def renew_analysis_job_lease(
    redis: Redis,
    lease: LeasedAnalysisJob,
    *,
    lease_timeout_seconds: int,
    now: datetime | None = None,
) -> LeasedAnalysisJob:
    """Extend a worker-owned lease and return the refreshed lease metadata."""
    leased_at_ms = _utc_now_ms(now)
    lease_timeout_ms = max(1, int(lease_timeout_seconds)) * 1000
    result = await redis.eval(
        _RENEW_LEASE_SCRIPT,
        2,
        LEASE_KEY_PREFIX,
        LEASE_EXPIRY_ZSET_KEY,
        lease.token,
        lease.worker_id,
        str(leased_at_ms),
        str(lease_timeout_ms),
    )
    if int(result) == -1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    if int(result) != 1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} no longer exists for worker {lease.worker_id!r}."
        )
    return LeasedAnalysisJob(
        token=lease.token,
        payload=lease.payload,
        raw_payload=lease.raw_payload,
        worker_id=lease.worker_id,
        leased_at_ms=leased_at_ms,
        lease_timeout_ms=lease_timeout_ms,
        expires_at_ms=leased_at_ms + lease_timeout_ms,
    )


async def schedule_analysis_job_retry(
    redis: Redis,
    lease: LeasedAnalysisJob,
    *,
    retry_at: datetime,
) -> bool:
    """Move a worker-owned lease into the scheduled retry queue."""
    result = await redis.eval(
        _SCHEDULE_RETRY_SCRIPT,
        4,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        RETRY_QUEUE_KEY,
        lease.token,
        lease.worker_id,
        str(lease.leased_at_ms),
        str(_utc_now_ms(retry_at)),
    )
    if int(result) == -1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    return int(result) == 1


async def promote_scheduled_analysis_jobs(
    redis: Redis,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    """Promote due scheduled retries back into the durable queue."""
    result = await redis.eval(
        _PROMOTE_RETRY_SCRIPT,
        2,
        QUEUE_KEY,
        RETRY_QUEUE_KEY,
        str(_utc_now_ms(now)),
        str(max(1, int(limit))),
    )
    return int(result or 0)


async def get_expired_analysis_job_leases(
    redis: Redis,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> list[LeasedAnalysisJob]:
    """Load expired lease records that are eligible for reaping."""
    now_ms = _utc_now_ms(now)
    tokens = await redis.zrangebyscore(
        LEASE_EXPIRY_ZSET_KEY,
        min=0,
        max=now_ms,
        start=0,
        num=max(1, int(limit)),
    )
    expired: list[LeasedAnalysisJob] = []
    for raw_token in tokens:
        token = _decode_text(raw_token)
        lease_data = await redis.hgetall(f"{LEASE_KEY_PREFIX}{token}")
        if not lease_data:
            continue

        normalized = {_decode_text(key): _decode_text(value) for key, value in lease_data.items()}
        raw_payload = normalized.get("raw")
        worker_id = normalized.get("worker_id")
        leased_at_ms = normalized.get("leased_at_ms")
        lease_timeout_ms = normalized.get("lease_timeout_ms")
        expires_at_ms = normalized.get("expires_at_ms")
        if not all((raw_payload, worker_id, leased_at_ms, lease_timeout_ms, expires_at_ms)):
            continue

        expired.append(
            LeasedAnalysisJob(
                token=token,
                payload=_parse_raw_payload(raw_payload),
                raw_payload=raw_payload,
                worker_id=worker_id,
                leased_at_ms=int(leased_at_ms),
                lease_timeout_ms=int(lease_timeout_ms),
                expires_at_ms=int(expires_at_ms),
            )
        )
    return expired


async def requeue_expired_analysis_job(redis: Redis, lease: LeasedAnalysisJob) -> bool:
    """Return an expired lease back to the durable queue."""
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        4,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        QUEUE_KEY,
        lease.token,
        str(lease.leased_at_ms),
        "requeue",
    )
    return int(result) == 1


async def move_analysis_job_to_dlq(
    redis: Redis,
    lease: LeasedAnalysisJob,
    *,
    attempt_count: int,
    reason: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Remove a leased job from processing and store its payload in the DLQ."""
    result = await redis.eval(
        _MOVE_TO_DLQ_SCRIPT,
        4,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        _build_dlq_key(lease.job_id),
        lease.token,
        lease.worker_id,
        str(lease.leased_at_ms),
        _serialize_dlq_payload(
            lease,
            attempt_count=attempt_count,
            reason=reason,
            now=now,
        ),
    )
    if int(result) == -1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    return int(result) == 1


async def get_dlq_job(redis: Redis, job_id: str) -> dict | None:
    """Return the stored DLQ payload for a job, or None if absent."""
    raw = await redis.get(_build_dlq_key(job_id))
    if raw is None:
        return None
    return _parse_dlq_payload(_decode_text(raw))


async def requeue_dlq_job(
    redis: Redis,
    *,
    job_id: str,
    max_depth: int | None = None,
) -> dict | None:
    """Requeue a DLQ job by id and remove it from DLQ on success."""
    dlq_key = _build_dlq_key(job_id)
    raw = await redis.get(dlq_key)
    if raw is None:
        return None

    payload = _parse_dlq_payload(_decode_text(raw))
    await _enqueue_raw_payload(
        redis,
        payload["raw_payload"],
        max_depth=max_depth,
    )
    await redis.delete(dlq_key)
    return payload


async def drop_expired_analysis_job(redis: Redis, lease: LeasedAnalysisJob) -> bool:
    """Discard an expired processing lease without requeueing it."""
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        4,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        QUEUE_KEY,
        lease.token,
        str(lease.leased_at_ms),
        "drop",
    )
    return int(result) == 1
