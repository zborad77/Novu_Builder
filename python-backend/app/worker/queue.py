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
import structlog

QUEUE_KEY = "analysis:jobs"
PROCESSING_QUEUE_KEY = "analysis:processing"
RETRY_QUEUE_KEY = "analysis:retry"
LEASE_KEY_PREFIX = "analysis:lease:"
LEASE_EXPIRY_ZSET_KEY = "analysis:lease_expiry"
LEASE_SEQUENCE_KEY = "analysis:lease_sequence"
DLQ_KEY_PREFIX = "analysis:dlq:"
DLQ_ACTIVE_SET_KEY = "analysis:dlq:active"
DLQ_HISTORY_SUFFIX = ":history"

logger = structlog.get_logger(__name__)
_JOB_PRIORITY_STANDARD = "standard"
_JOB_PRIORITY_CRITICAL = "critical"

_LEASE_JOB_SCRIPT = """
local total_processing = redis.call('LLEN', KEYS[2]) + redis.call('LLEN', KEYS[3])
if total_processing >= tonumber(ARGV[4]) then
    return {'__backpressure__', tostring(total_processing)}
end

local raw = redis.call('LPOP', KEYS[1])
if not raw then
    return nil
end

local token = tostring(redis.call('INCR', KEYS[6]))
local lease_key = KEYS[5] .. token
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
redis.call('ZADD', KEYS[4], expires_at_ms, token)
return {token, raw, worker_id, leased_at_ms, lease_timeout_ms, expires_at_ms}
"""

_QUEUE_CAPACITY_GUARD_LUA = """
local function check_queue_capacity(queue_key, processing_key, peer_queue_key, max_depth, max_global_queued, delta)
    local queue_depth = redis.call('LLEN', queue_key)
    local processing_depth = redis.call('LLEN', processing_key)
    if (queue_depth + processing_depth + delta) > max_depth then
        return {0, queue_depth, processing_depth, queue_depth + redis.call('LLEN', peer_queue_key)}
    end
    local global_queued = queue_depth + redis.call('LLEN', peer_queue_key)
    if (global_queued + delta) > max_global_queued then
        return {-2, queue_depth, processing_depth, global_queued}
    end
    return {1, queue_depth, processing_depth, global_queued}
end

local function guarded_push(queue_key, processing_key, peer_queue_key, raw, max_depth, max_global_queued, delta, priority)
    local guard = check_queue_capacity(queue_key, processing_key, peer_queue_key, max_depth, max_global_queued, delta)
    if tonumber(guard[1]) ~= 1 then
        return guard
    end

    if priority == 'critical' then
        redis.call('LPUSH', queue_key, raw)
    else
        redis.call('RPUSH', queue_key, raw)
    end
    return {1, guard[2] + 1, guard[3], guard[4] + 1}
end
"""

_ENQUEUE_WITH_LIMIT_SCRIPT = _QUEUE_CAPACITY_GUARD_LUA + """
return guarded_push(KEYS[1], KEYS[2], KEYS[3], ARGV[1], tonumber(ARGV[2]), tonumber(ARGV[3]), 1, ARGV[4])
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

_FINALIZE_EXPIRED_LEASE_SCRIPT = _QUEUE_CAPACITY_GUARD_LUA + """
local token = ARGV[1]
local expected_leased_at_ms = ARGV[2]
local action = ARGV[3]
local max_depth = tonumber(ARGV[4])
local lease_key = KEYS[1] .. token
if redis.call('EXISTS', lease_key) == 0 then
    return {-3, 0, 0, 0}
end

local actual_leased_at_ms = redis.call('HGET', lease_key, 'leased_at_ms')
if actual_leased_at_ms ~= expected_leased_at_ms then
    return {-3, 0, 0, 0}
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    if action == 'requeue' then
        local queue_depth = redis.call('LLEN', KEYS[4])
        local processing_depth = redis.call('LLEN', KEYS[2])
        local global_queued = queue_depth + redis.call('LLEN', KEYS[5])
        if (queue_depth + processing_depth) > max_depth then
            return {0, queue_depth, processing_depth, global_queued}
        end
        if (global_queued + 1) > tonumber(ARGV[5]) then
            return {-2, queue_depth, processing_depth, global_queued}
        end
    end

    redis.call('LREM', KEYS[2], 1, raw)
    if action == 'requeue' then
        if ARGV[6] == 'critical' then
            redis.call('LPUSH', KEYS[4], raw)
        else
            redis.call('RPUSH', KEYS[4], raw)
        end
    end
end

redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], token)
return {1, 0, 0, redis.call('LLEN', KEYS[4]) + redis.call('LLEN', KEYS[5])}
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
redis.call('RPUSH', KEYS[4], ARGV[4])
redis.call('SADD', KEYS[5], ARGV[5])
redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""

_PROMOTE_RETRY_SCRIPT = _QUEUE_CAPACITY_GUARD_LUA + """
local due = redis.call('ZRANGEBYSCORE', KEYS[3], 0, ARGV[1], 'LIMIT', 0, ARGV[2])
local moved = 0

for _, raw in ipairs(due) do
    local enqueue_result = guarded_push(KEYS[1], KEYS[2], KEYS[4], raw, tonumber(ARGV[3]), tonumber(ARGV[4]), 1, 'standard')
    if tonumber(enqueue_result[1]) ~= 1 then
        return {moved, #due - moved, enqueue_result[2], enqueue_result[3], enqueue_result[4]}
    end

    if redis.call('ZREM', KEYS[3], raw) == 1 then
        moved = moved + 1
    else
        redis.call('LREM', KEYS[1], 1, raw)
    end
end
return {moved, 0, redis.call('LLEN', KEYS[1]), redis.call('LLEN', KEYS[2]), redis.call('LLEN', KEYS[1]) + redis.call('LLEN', KEYS[4])}
"""


class InvalidAnalysisJobPayloadError(ValueError):
    """Raised when a Redis queue item cannot be decoded into the expected payload."""


class LostAnalysisJobLeaseError(RuntimeError):
    """Raised when a worker attempts to ACK/renew a lease it no longer owns."""


class AnalysisJobQueueCapacityExceededError(RuntimeError):
    """Raised when enqueue would push the analysis queue beyond the configured cap."""

    def __init__(
        self,
        *,
        queued: int,
        processing: int,
        max_depth: int,
        scope: str = "lane",
        global_queued: int | None = None,
        max_global_queued: int | None = None,
    ) -> None:
        total = queued + processing
        if scope == "global" and global_queued is not None and max_global_queued is not None:
            super().__init__(
                f"Analysis queue rejected by global backpressure ({global_queued}/{max_global_queued} queued)."
            )
        else:
            super().__init__(
                f"Analysis queue is full ({total}/{max_depth}; queued={queued}, processing={processing})."
            )
        self.queued = queued
        self.processing = processing
        self.max_depth = max_depth
        self.scope = scope
        self.global_queued = global_queued
        self.max_global_queued = max_global_queued


def _build_dlq_key(job_id: str) -> str:
    return f"{DLQ_KEY_PREFIX}{job_id}"


def _build_dlq_history_key(job_id: str) -> str:
    return f"{_build_dlq_key(job_id)}{DLQ_HISTORY_SUFFIX}"


class AnalysisJobQueuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    project_id: str
    organization_id: str | None = None
    is_superadmin_context: bool = False
    priority: str = _JOB_PRIORITY_STANDARD

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

    @field_validator("priority")
    @classmethod
    def _validate_priority(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {_JOB_PRIORITY_STANDARD, _JOB_PRIORITY_CRITICAL}:
            raise ValueError("must be one of: standard, critical")
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
    def priority(self) -> str:
        return str(self.payload.get("priority", _JOB_PRIORITY_STANDARD))

    @property
    def lease_timeout_seconds(self) -> int:
        return max(1, self.lease_timeout_ms // 1000)


@dataclass(frozen=True)
class AnalysisJobTransportSnapshot:
    queued: tuple[tuple[str, str], ...]
    processing: tuple[LeasedAnalysisJob, ...]
    scheduled_retry: tuple[tuple[str, str], ...]
    dlq_job_ids: frozenset[str]

    def queued_job_ids(self) -> frozenset[str]:
        return frozenset(job_id for job_id, _ in self.queued)

    def processing_job_ids(self) -> frozenset[str]:
        return frozenset(lease.job_id for lease in self.processing)

    def scheduled_retry_job_ids(self) -> frozenset[str]:
        return frozenset(job_id for job_id, _ in self.scheduled_retry)

    def has_any_entry(self, job_id: str) -> bool:
        normalized = str(job_id)
        return (
            normalized in self.queued_job_ids()
            or normalized in self.processing_job_ids()
            or normalized in self.scheduled_retry_job_ids()
            or normalized in self.dlq_job_ids
        )

    def get_processing_lease(self, job_id: str) -> LeasedAnalysisJob | None:
        normalized = str(job_id)
        for lease in self.processing:
            if lease.job_id == normalized:
                return lease
        return None


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


def _parse_capacity_eval_result(
    result: object,
    *,
    operation: str,
) -> tuple[int, int, int, int]:
    if not isinstance(result, (list, tuple)) or len(result) != 4:
        raise RuntimeError(f"Unexpected Redis response while executing {operation}.")
    return (
        int(_decode_text(result[0])),
        int(_decode_text(result[1])),
        int(_decode_text(result[2])),
        int(_decode_text(result[3])),
    )


def _parse_retry_promotion_eval_result(result: object) -> tuple[int, int, int, int, int]:
    if not isinstance(result, (list, tuple)) or len(result) != 5:
        raise RuntimeError("Unexpected Redis response while promoting scheduled analysis jobs.")
    return (
        int(_decode_text(result[0])),
        int(_decode_text(result[1])),
        int(_decode_text(result[2])),
        int(_decode_text(result[3])),
        int(_decode_text(result[4])),
    )


async def _enqueue_raw_payload(
    redis: Redis,
    raw_payload: str,
    *,
    max_depth: int | None = None,
    max_global_queued: int | None = None,
    priority: str = _JOB_PRIORITY_STANDARD,
) -> None:
    normalized_priority = (
        _JOB_PRIORITY_CRITICAL
        if priority == _JOB_PRIORITY_CRITICAL
        else _JOB_PRIORITY_STANDARD
    )
    if max_depth is None:
        if normalized_priority == _JOB_PRIORITY_CRITICAL:
            await redis.lpush(QUEUE_KEY, raw_payload)
        else:
            await redis.rpush(QUEUE_KEY, raw_payload)
        return

    result = await redis.eval(
        _ENQUEUE_WITH_LIMIT_SCRIPT,
        3,
        QUEUE_KEY,
        PROCESSING_QUEUE_KEY,
        "heavy:jobs",
        raw_payload,
        str(max(1, int(max_depth))),
        str(max(1, int(max_global_queued or 1_000_000))),
        normalized_priority,
    )
    status, queued, processing, global_queued = _parse_capacity_eval_result(
        result,
        operation="analysis queue enqueue",
    )
    if status != 1:
        raise AnalysisJobQueueCapacityExceededError(
            queued=queued,
            processing=processing,
            max_depth=max(1, int(max_depth)),
            scope="global" if status == -2 else "lane",
            global_queued=global_queued,
            max_global_queued=max(1, int(max_global_queued or 1_000_000)),
        )


async def inspect_analysis_job_transport(redis: Redis | None) -> AnalysisJobTransportSnapshot:
    """Return a best-effort snapshot of Redis transport state for reconciliation."""
    if redis is None:
        return AnalysisJobTransportSnapshot(
            queued=(),
            processing=(),
            scheduled_retry=(),
            dlq_job_ids=frozenset(),
        )

    queued_entries: list[tuple[str, str]] = []
    for raw in await redis.lrange(QUEUE_KEY, 0, -1):
        raw_payload = _decode_text(raw)
        try:
            payload = _parse_raw_payload(raw_payload)
        except InvalidAnalysisJobPayloadError:
            continue
        queued_entries.append((str(payload["job_id"]), raw_payload))

    processing_entries: list[LeasedAnalysisJob] = []
    processing_tokens = await redis.zrange(LEASE_EXPIRY_ZSET_KEY, 0, -1)
    lease_payloads: dict[str, dict[str, str]] = {}
    for raw_token in processing_tokens:
        token = _decode_text(raw_token)
        candidate = await redis.hgetall(f"{LEASE_KEY_PREFIX}{token}")
        if not candidate:
            continue
        lease_payloads[token] = {_decode_text(key): _decode_text(value) for key, value in candidate.items()}

    for raw in await redis.lrange(PROCESSING_QUEUE_KEY, 0, -1):
        raw_payload = _decode_text(raw)
        try:
            payload = _parse_raw_payload(raw_payload)
        except InvalidAnalysisJobPayloadError:
            continue

        lease_token = ""
        lease_data: dict[str, str] | None = None
        for token, normalized in lease_payloads.items():
            if normalized.get("raw") == raw_payload:
                lease_token = token
                lease_data = normalized
                break

        if lease_data is None:
            processing_entries.append(
                LeasedAnalysisJob(
                    token="",
                    payload=payload,
                    raw_payload=raw_payload,
                    worker_id="",
                    leased_at_ms=0,
                    lease_timeout_ms=0,
                    expires_at_ms=0,
                )
            )
            continue

        try:
            processing_entries.append(
                LeasedAnalysisJob(
                    token=lease_token or lease_data.get("token", ""),
                    payload=payload,
                    raw_payload=raw_payload,
                    worker_id=lease_data.get("worker_id", ""),
                    leased_at_ms=int(lease_data.get("leased_at_ms", "0")),
                    lease_timeout_ms=int(lease_data.get("lease_timeout_ms", "0")),
                    expires_at_ms=int(lease_data.get("expires_at_ms", "0")),
                )
            )
        except (TypeError, ValueError):
            continue

    scheduled_retry_entries: list[tuple[str, str]] = []
    for raw in await redis.zrange(RETRY_QUEUE_KEY, 0, -1):
        raw_payload = _decode_text(raw)
        try:
            payload = _parse_raw_payload(raw_payload)
        except InvalidAnalysisJobPayloadError:
            continue
        scheduled_retry_entries.append((str(payload["job_id"]), raw_payload))

    dlq_values = await redis.smembers(DLQ_ACTIVE_SET_KEY)
    dlq_job_ids = frozenset(_decode_text(value) for value in dlq_values)

    return AnalysisJobTransportSnapshot(
        queued=tuple(queued_entries),
        processing=tuple(processing_entries),
        scheduled_retry=tuple(scheduled_retry_entries),
        dlq_job_ids=dlq_job_ids,
    )


async def purge_analysis_job_transport(
    redis: Redis | None,
    *,
    job_id: str,
    snapshot: AnalysisJobTransportSnapshot | None = None,
) -> None:
    """Remove queued/processing/retry/DLQ transport remnants for a DB-authoritative job id."""
    if redis is None:
        return

    transport = snapshot or await inspect_analysis_job_transport(redis)
    normalized_job_id = str(job_id)

    for queued_job_id, raw_payload in transport.queued:
        if queued_job_id == normalized_job_id:
            await redis.lrem(QUEUE_KEY, 0, raw_payload)

    for lease in transport.processing:
        if lease.job_id != normalized_job_id:
            continue
        if lease.raw_payload:
            await redis.lrem(PROCESSING_QUEUE_KEY, 0, lease.raw_payload)
        if lease.token:
            await redis.delete(f"{LEASE_KEY_PREFIX}{lease.token}")
            await redis.zrem(LEASE_EXPIRY_ZSET_KEY, lease.token)

    for retry_job_id, raw_payload in transport.scheduled_retry:
        if retry_job_id == normalized_job_id:
            await redis.zrem(RETRY_QUEUE_KEY, raw_payload)

    if normalized_job_id in transport.dlq_job_ids:
        await redis.srem(DLQ_ACTIVE_SET_KEY, normalized_job_id)


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
    max_global_queued: int | None = None,
    priority: str = _JOB_PRIORITY_STANDARD,
) -> None:
    """Push a validated job payload to the tail of the durable Redis queue."""
    payload = validate_analysis_job_payload(
        {
            "job_id": job_id,
            "project_id": project_id,
            "organization_id": organization_id,
            "is_superadmin_context": is_superadmin_context,
            "priority": priority,
        }
    )
    await _enqueue_raw_payload(
        redis,
        json.dumps(payload.model_dump()),
        max_depth=max_depth,
        max_global_queued=max_global_queued,
        priority=payload.priority,
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
    max_concurrent_jobs: int | None = None,
    now: datetime | None = None,
) -> LeasedAnalysisJob | None:
    """Lease the next queued job, or return None when the queue is empty."""
    lease_timeout_ms = max(1, int(lease_timeout_seconds)) * 1000
    result = await redis.eval(
        _LEASE_JOB_SCRIPT,
        6,
        QUEUE_KEY,
        PROCESSING_QUEUE_KEY,
        "heavy:processing",
        LEASE_EXPIRY_ZSET_KEY,
        LEASE_KEY_PREFIX,
        LEASE_SEQUENCE_KEY,
        str(_utc_now_ms(now)),
        worker_id,
        str(lease_timeout_ms),
        str(max(1, int(max_concurrent_jobs or 1_000_000))),
    )
    if result is None:
        return None
    if (
        isinstance(result, (list, tuple))
        and len(result) == 2
        and _decode_text(result[0]) == "__backpressure__"
    ):
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
    max_depth: int,
    max_global_queued: int | None = None,
) -> int:
    """Promote due scheduled retries back into the durable queue."""
    result = await redis.eval(
        _PROMOTE_RETRY_SCRIPT,
        4,
        QUEUE_KEY,
        PROCESSING_QUEUE_KEY,
        RETRY_QUEUE_KEY,
        "heavy:jobs",
        str(_utc_now_ms(now)),
        str(max(1, int(limit))),
        str(max(1, int(max_depth))),
        str(max(1, int(max_global_queued or 1_000_000))),
    )
    moved, blocked, queued, processing, global_queued = _parse_retry_promotion_eval_result(result)
    if blocked > 0:
        logger.warning(
            "analysis_queue.retry_promotion_capacity_blocked",
            moved=moved,
            blocked=blocked,
            queued=queued,
            processing=processing,
            global_queued=global_queued,
            max_depth=max(1, int(max_depth)),
            max_global_queued=max(1, int(max_global_queued or 1_000_000)),
        )
    return moved


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


async def requeue_expired_analysis_job(
    redis: Redis,
    lease: LeasedAnalysisJob,
    *,
    max_depth: int,
    max_global_queued: int | None = None,
) -> bool:
    """Return an expired lease back to the durable queue."""
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        5,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        QUEUE_KEY,
        "heavy:jobs",
        lease.token,
        str(lease.leased_at_ms),
        "requeue",
        str(max(1, int(max_depth))),
        str(max(1, int(max_global_queued or 1_000_000))),
        lease.priority,
    )
    status, queued, processing, global_queued = _parse_capacity_eval_result(
        result,
        operation="expired analysis job requeue",
    )
    if status in {0, -2}:
        raise AnalysisJobQueueCapacityExceededError(
            queued=queued,
            processing=processing,
            max_depth=max(1, int(max_depth)),
            scope="global" if status == -2 else "lane",
            global_queued=global_queued,
            max_global_queued=max(1, int(max_global_queued or 1_000_000)),
        )
    return status == 1


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
        5,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        _build_dlq_history_key(lease.job_id),
        DLQ_ACTIVE_SET_KEY,
        lease.token,
        lease.worker_id,
        str(lease.leased_at_ms),
        _serialize_dlq_payload(
            lease,
            attempt_count=attempt_count,
            reason=reason,
            now=now,
        ),
        lease.job_id,
    )
    if int(result) == -1:
        raise LostAnalysisJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    return int(result) == 1


async def get_dlq_job(redis: Redis, job_id: str) -> dict | None:
    """Return the stored DLQ payload for a job, or None if absent."""
    if await redis.sismember(DLQ_ACTIVE_SET_KEY, job_id):
        raw = await redis.lindex(_build_dlq_history_key(job_id), -1)
        if raw is None:
            return None
        return _parse_dlq_payload(_decode_text(raw))

    # Backward-compatible fallback for legacy one-value DLQ entries.
    legacy_raw = await redis.get(_build_dlq_key(job_id))
    if legacy_raw is None:
        return None
    return _parse_dlq_payload(_decode_text(legacy_raw))


async def requeue_dlq_job(
    redis: Redis,
    *,
    job_id: str,
    max_depth: int | None = None,
    max_global_queued: int | None = None,
) -> dict | None:
    """Requeue a DLQ job by id and remove it from DLQ on success."""
    raw = None
    if await redis.sismember(DLQ_ACTIVE_SET_KEY, job_id):
        raw = await redis.lindex(_build_dlq_history_key(job_id), -1)
    else:
        raw = await redis.get(_build_dlq_key(job_id))
    if raw is None:
        return None

    payload = _parse_dlq_payload(_decode_text(raw))
    await _enqueue_raw_payload(
        redis,
        payload["raw_payload"],
        max_depth=max_depth,
        max_global_queued=max_global_queued,
    )
    if await redis.sismember(DLQ_ACTIVE_SET_KEY, job_id):
        await redis.srem(DLQ_ACTIVE_SET_KEY, job_id)
    else:
        await redis.delete(_build_dlq_key(job_id))
    return payload


async def drop_expired_analysis_job(redis: Redis, lease: LeasedAnalysisJob) -> bool:
    """Discard an expired processing lease without requeueing it."""
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        5,
        LEASE_KEY_PREFIX,
        PROCESSING_QUEUE_KEY,
        LEASE_EXPIRY_ZSET_KEY,
        QUEUE_KEY,
        "heavy:jobs",
        lease.token,
        str(lease.leased_at_ms),
        "drop",
        "0",
        "1",
        lease.priority,
    )
    status, _, _, _ = _parse_capacity_eval_result(
        result,
        operation="expired analysis job drop",
    )
    return status == 1
