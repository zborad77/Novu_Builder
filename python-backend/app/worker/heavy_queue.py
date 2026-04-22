"""Redis-backed heavy workload queue for export generation and media transforms.

This lane is intentionally separate from the main analysis queue:
  - analysis keeps its own throughput and lease/reaper discipline
  - heavyweight export/media work uses a dedicated queue namespace and worker slots

The transport contract mirrors the analysis queue in one important respect:
mutating operations are never replayed implicitly after transport failures.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json

from app.case_orchestration.dispatch_guard import assert_dispatch_allowed
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from redis.asyncio import Redis

HEAVY_QUEUE_KEY = "heavy:jobs"
HEAVY_PROCESSING_QUEUE_KEY = "heavy:processing"
HEAVY_LEASE_KEY_PREFIX = "heavy:lease:"
HEAVY_LEASE_EXPIRY_ZSET_KEY = "heavy:lease_expiry"
HEAVY_LEASE_SEQUENCE_KEY = "heavy:lease_sequence"
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

_ENQUEUE_WITH_LIMIT_SCRIPT = """
local queue_depth = redis.call('LLEN', KEYS[1])
local processing_depth = redis.call('LLEN', KEYS[2])
local max_depth = tonumber(ARGV[2])
local global_queued = queue_depth + redis.call('LLEN', KEYS[3])
if (queue_depth + processing_depth + 1) > max_depth then
    return {0, queue_depth, processing_depth, global_queued}
end
if (global_queued + 1) > tonumber(ARGV[3]) then
    return {-2, queue_depth, processing_depth, global_queued}
end

if ARGV[4] == 'critical' then
    redis.call('LPUSH', KEYS[1], ARGV[1])
else
    redis.call('RPUSH', KEYS[1], ARGV[1])
end
return {1, queue_depth + 1, processing_depth, global_queued + 1}
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

_FINALIZE_EXPIRED_LEASE_SCRIPT = """
local token = ARGV[1]
local expected_leased_at_ms = ARGV[2]
local action = ARGV[3]
local lease_key = KEYS[1] .. token
if redis.call('EXISTS', lease_key) == 0 then
    return -3
end

local actual_leased_at_ms = redis.call('HGET', lease_key, 'leased_at_ms')
if actual_leased_at_ms ~= expected_leased_at_ms then
    return -3
end

local raw = redis.call('HGET', lease_key, 'raw')
if raw then
    if action == 'requeue' then
        local queue_depth = redis.call('LLEN', KEYS[4])
        local processing_depth = redis.call('LLEN', KEYS[2])
        local global_queued = queue_depth + redis.call('LLEN', KEYS[5])
        if (queue_depth + processing_depth) > tonumber(ARGV[4]) then
            return 0
        end
        if (global_queued + 1) > tonumber(ARGV[5]) then
            return -2
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
return 1
"""


class InvalidHeavyJobPayloadError(ValueError):
    """Raised when a heavy queue item cannot be decoded into the expected payload."""


class LostHeavyJobLeaseError(RuntimeError):
    """Raised when a worker attempts to ACK/renew a heavy lease it no longer owns."""


class HeavyJobQueueCapacityExceededError(RuntimeError):
    """Raised when enqueue would push the heavy queue beyond the configured cap."""

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
                f"Heavy queue rejected by global backpressure ({global_queued}/{max_global_queued} queued)."
            )
        else:
            super().__init__(
                f"Heavy queue is full ({total}/{max_depth}; queued={queued}, processing={processing})."
            )
        self.queued = queued
        self.processing = processing
        self.max_depth = max_depth
        self.scope = scope
        self.global_queued = global_queued
        self.max_global_queued = max_global_queued


class HeavyJobQueuePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_type: str
    project_id: str
    organization_id: str | None = None
    export_id: str | None = None
    photo_id: str | None = None
    priority: str = _JOB_PRIORITY_STANDARD

    @field_validator("job_type")
    @classmethod
    def _validate_job_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"export_generate", "photo_variant_processing"}:
            raise ValueError("must be one of: export_generate, photo_variant_processing")
        return normalized

    @field_validator("project_id")
    @classmethod
    def _validate_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must be a non-empty string")
        return normalized

    @field_validator("organization_id", "export_id", "photo_id")
    @classmethod
    def _validate_optional_identifier(cls, value: str | None) -> str | None:
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
    def _validate_subject(self) -> "HeavyJobQueuePayload":
        if self.job_type == "export_generate":
            if self.export_id is None:
                raise ValueError("export_id is required for export_generate")
            if self.photo_id is not None:
                raise ValueError("photo_id is not allowed for export_generate")
        elif self.job_type == "photo_variant_processing":
            if self.photo_id is None:
                raise ValueError("photo_id is required for photo_variant_processing")
            if self.export_id is not None:
                raise ValueError("export_id is not allowed for photo_variant_processing")
        return self


@dataclass(frozen=True)
class LeasedHeavyJob:
    token: str
    payload: dict
    raw_payload: str
    worker_id: str
    leased_at_ms: int
    lease_timeout_ms: int
    expires_at_ms: int

    @property
    def job_type(self) -> str:
        return str(self.payload["job_type"])

    @property
    def project_id(self) -> str:
        return str(self.payload["project_id"])

    @property
    def organization_id(self) -> str | None:
        value = self.payload.get("organization_id")
        return None if value is None else str(value)

    @property
    def export_id(self) -> str | None:
        value = self.payload.get("export_id")
        return None if value is None else str(value)

    @property
    def photo_id(self) -> str | None:
        value = self.payload.get("photo_id")
        return None if value is None else str(value)

    @property
    def priority(self) -> str:
        return str(self.payload.get("priority", _JOB_PRIORITY_STANDARD))


@dataclass(frozen=True)
class HeavyJobTransportSnapshot:
    queued: tuple[tuple[str, str, str | None, str | None, str], ...]
    processing: tuple[LeasedHeavyJob, ...]

    def has_export(self, export_id: str) -> bool:
        normalized = str(export_id)
        return any(
            queued_export_id == normalized
            for _, _, queued_export_id, _, _ in self.queued
        ) or any(lease.export_id == normalized for lease in self.processing)

    def has_photo(self, photo_id: str) -> bool:
        normalized = str(photo_id)
        return any(
            queued_photo_id == normalized
            for _, _, _, queued_photo_id, _ in self.queued
        ) or any(lease.photo_id == normalized for lease in self.processing)


def _utc_now_ms(now: datetime | None = None) -> int:
    current = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return int(current.timestamp() * 1000)


def _decode_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def validate_heavy_job_payload(payload: object) -> HeavyJobQueuePayload:
    try:
        return HeavyJobQueuePayload.model_validate(payload)
    except ValidationError as exc:
        issues: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", ())) or "payload"
            issue_message = str(error.get("msg", error.get("type", "invalid")))
            issues.append(f"{location}:{issue_message}")
        summary = "; ".join(issues) if issues else "invalid_payload"
        raise InvalidHeavyJobPayloadError(summary) from exc


def _parse_raw_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidHeavyJobPayloadError(
            "Invalid heavy job queue payload: malformed JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise InvalidHeavyJobPayloadError(
            "Invalid heavy job queue payload: expected a JSON object."
        )
    return validate_heavy_job_payload(payload).model_dump()


def _leased_job_from_redis_result(result: object) -> LeasedHeavyJob:
    if not isinstance(result, (list, tuple)) or len(result) != 6:
        raise InvalidHeavyJobPayloadError("Invalid heavy job lease result from Redis.")

    token = _decode_text(result[0])
    raw_payload = _decode_text(result[1])
    worker_id = _decode_text(result[2])
    leased_at_ms = int(_decode_text(result[3]))
    lease_timeout_ms = int(_decode_text(result[4]))
    expires_at_ms = int(_decode_text(result[5]))
    payload = _parse_raw_payload(raw_payload)
    return LeasedHeavyJob(
        token=token,
        payload=payload,
        raw_payload=raw_payload,
        worker_id=worker_id,
        leased_at_ms=leased_at_ms,
        lease_timeout_ms=lease_timeout_ms,
        expires_at_ms=expires_at_ms,
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
            await redis.lpush(HEAVY_QUEUE_KEY, raw_payload)
        else:
            await redis.rpush(HEAVY_QUEUE_KEY, raw_payload)
        return

    result = await redis.eval(
        _ENQUEUE_WITH_LIMIT_SCRIPT,
        3,
        HEAVY_QUEUE_KEY,
        HEAVY_PROCESSING_QUEUE_KEY,
        "analysis:jobs",
        raw_payload,
        str(max(1, int(max_depth))),
        str(max(1, int(max_global_queued or 1_000_000))),
        normalized_priority,
    )
    if (
        not isinstance(result, (list, tuple))
        or len(result) != 4
        or int(_decode_text(result[0])) != 1
    ):
        queued = int(_decode_text(result[1])) if isinstance(result, (list, tuple)) and len(result) > 1 else 0
        processing = int(_decode_text(result[2])) if isinstance(result, (list, tuple)) and len(result) > 2 else 0
        global_queued = int(_decode_text(result[3])) if isinstance(result, (list, tuple)) and len(result) > 3 else None
        status = int(_decode_text(result[0])) if isinstance(result, (list, tuple)) and len(result) > 0 else 0
        raise HeavyJobQueueCapacityExceededError(
            queued=queued,
            processing=processing,
            max_depth=max(1, int(max_depth)),
            scope="global" if status == -2 else "lane",
            global_queued=global_queued,
            max_global_queued=max(1, int(max_global_queued or 1_000_000)),
        )


async def inspect_heavy_job_transport(redis: Redis | None) -> HeavyJobTransportSnapshot:
    if redis is None:
        return HeavyJobTransportSnapshot(queued=(), processing=())

    queued_entries: list[tuple[str, str, str | None, str | None, str]] = []
    for raw in await redis.lrange(HEAVY_QUEUE_KEY, 0, -1):
        raw_payload = _decode_text(raw)
        try:
            payload = _parse_raw_payload(raw_payload)
        except InvalidHeavyJobPayloadError:
            continue
        queued_entries.append(
            (
                str(payload["job_type"]),
                str(payload["project_id"]),
                payload.get("export_id"),
                payload.get("photo_id"),
                raw_payload,
            )
        )

    processing_entries: list[LeasedHeavyJob] = []
    processing_tokens = await redis.zrange(HEAVY_LEASE_EXPIRY_ZSET_KEY, 0, -1)
    lease_payloads: dict[str, dict[str, str]] = {}
    for raw_token in processing_tokens:
        token = _decode_text(raw_token)
        values = await redis.hgetall(f"{HEAVY_LEASE_KEY_PREFIX}{token}")
        if not values:
            continue
        lease_payloads[token] = {_decode_text(key): _decode_text(value) for key, value in values.items()}

    for raw in await redis.lrange(HEAVY_PROCESSING_QUEUE_KEY, 0, -1):
        raw_payload = _decode_text(raw)
        try:
            payload = _parse_raw_payload(raw_payload)
        except InvalidHeavyJobPayloadError:
            continue

        matching_token = None
        matching_values: dict[str, str] | None = None
        for token, values in lease_payloads.items():
            if values.get("raw") == raw_payload:
                matching_token = token
                matching_values = values
                break

        if matching_values is None:
            processing_entries.append(
                LeasedHeavyJob(
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
                LeasedHeavyJob(
                    token=matching_token or "",
                    payload=payload,
                    raw_payload=raw_payload,
                    worker_id=matching_values.get("worker_id", ""),
                    leased_at_ms=int(matching_values.get("leased_at_ms", "0")),
                    lease_timeout_ms=int(matching_values.get("lease_timeout_ms", "0")),
                    expires_at_ms=int(matching_values.get("expires_at_ms", "0")),
                )
            )
        except (TypeError, ValueError):
            continue

    return HeavyJobTransportSnapshot(
        queued=tuple(queued_entries),
        processing=tuple(processing_entries),
    )


async def enqueue_heavy_job(
    redis: Redis,
    *,
    job_type: str,
    project_id: str,
    organization_id: str | None = None,
    export_id: str | None = None,
    photo_id: str | None = None,
    dispatch_name: str = "worker.enqueue_job",
    max_depth: int | None = None,
    max_global_queued: int | None = None,
    priority: str = _JOB_PRIORITY_STANDARD,
) -> None:
    assert_dispatch_allowed(dispatch_name)
    payload = validate_heavy_job_payload(
        {
            "job_type": job_type,
            "project_id": project_id,
            "organization_id": organization_id,
            "export_id": export_id,
            "photo_id": photo_id,
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


async def get_heavy_job_queue_counts(redis: Redis) -> tuple[int, int]:
    if redis is None:
        return 0, 0
    queued = int(await redis.llen(HEAVY_QUEUE_KEY))
    processing = int(await redis.llen(HEAVY_PROCESSING_QUEUE_KEY))
    return queued, processing


async def dequeue_heavy_job(
    redis: Redis,
    *,
    worker_id: str,
    lease_timeout_seconds: int,
    max_concurrent_jobs: int | None = None,
    now: datetime | None = None,
) -> LeasedHeavyJob | None:
    lease_timeout_ms = max(1, int(lease_timeout_seconds)) * 1000
    result = await redis.eval(
        _LEASE_JOB_SCRIPT,
        6,
        HEAVY_QUEUE_KEY,
        HEAVY_PROCESSING_QUEUE_KEY,
        "analysis:processing",
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        HEAVY_LEASE_KEY_PREFIX,
        HEAVY_LEASE_SEQUENCE_KEY,
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


async def ack_heavy_job(redis: Redis, lease: LeasedHeavyJob) -> bool:
    result = await redis.eval(
        _ACK_JOB_SCRIPT,
        3,
        HEAVY_LEASE_KEY_PREFIX,
        HEAVY_PROCESSING_QUEUE_KEY,
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        lease.token,
        lease.worker_id,
    )
    if int(result) == -1:
        raise LostHeavyJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    return int(result) == 1


async def renew_heavy_job_lease(
    redis: Redis,
    lease: LeasedHeavyJob,
    *,
    lease_timeout_seconds: int,
    now: datetime | None = None,
) -> LeasedHeavyJob:
    lease_timeout_ms = max(1, int(lease_timeout_seconds)) * 1000
    leased_at_ms = _utc_now_ms(now)
    result = await redis.eval(
        _RENEW_LEASE_SCRIPT,
        2,
        HEAVY_LEASE_KEY_PREFIX,
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        lease.token,
        lease.worker_id,
        str(leased_at_ms),
        str(lease_timeout_ms),
    )
    numeric = int(result)
    if numeric == -1:
        raise LostHeavyJobLeaseError(
            f"Lease {lease.token} is no longer owned by worker {lease.worker_id!r}."
        )
    if numeric == 0:
        raise LostHeavyJobLeaseError(
            f"Lease {lease.token} no longer exists for worker {lease.worker_id!r}."
        )
    return LeasedHeavyJob(
        token=lease.token,
        payload=lease.payload,
        raw_payload=lease.raw_payload,
        worker_id=lease.worker_id,
        leased_at_ms=leased_at_ms,
        lease_timeout_ms=lease_timeout_ms,
        expires_at_ms=leased_at_ms + lease_timeout_ms,
    )


async def get_expired_heavy_job_leases(
    redis: Redis,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> list[LeasedHeavyJob]:
    now_ms = _utc_now_ms(now)
    tokens = await redis.zrangebyscore(
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        min=0,
        max=now_ms,
        start=0,
        num=max(1, limit),
    )
    leases: list[LeasedHeavyJob] = []
    for raw_token in tokens:
        token = _decode_text(raw_token)
        lease_key = f"{HEAVY_LEASE_KEY_PREFIX}{token}"
        values = await redis.hmget(
            lease_key,
            "token",
            "raw",
            "worker_id",
            "leased_at_ms",
            "lease_timeout_ms",
            "expires_at_ms",
        )
        if not values or any(value is None for value in values):
            continue
        try:
            leases.append(_leased_job_from_redis_result(values))
        except InvalidHeavyJobPayloadError:
            continue
    return leases


async def requeue_expired_heavy_job(
    redis: Redis,
    lease: LeasedHeavyJob,
    *,
    max_depth: int,
    max_global_queued: int | None = None,
) -> bool:
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        5,
        HEAVY_LEASE_KEY_PREFIX,
        HEAVY_PROCESSING_QUEUE_KEY,
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        HEAVY_QUEUE_KEY,
        "analysis:jobs",
        lease.token,
        str(lease.leased_at_ms),
        "requeue",
        str(max(1, int(max_depth))),
        str(max(1, int(max_global_queued or 1_000_000))),
        lease.priority,
    )
    numeric = int(result)
    if numeric in {0, -2}:
        raise HeavyJobQueueCapacityExceededError(
            queued=int(await redis.llen(HEAVY_QUEUE_KEY)),
            processing=int(await redis.llen(HEAVY_PROCESSING_QUEUE_KEY)),
            max_depth=max(1, int(max_depth)),
            scope="global" if numeric == -2 else "lane",
            global_queued=int(await redis.llen(HEAVY_QUEUE_KEY)) + int(await redis.llen("analysis:jobs")),
            max_global_queued=max(1, int(max_global_queued or 1_000_000)),
        )
    return numeric == 1


async def drop_expired_heavy_job(redis: Redis, lease: LeasedHeavyJob) -> bool:
    result = await redis.eval(
        _FINALIZE_EXPIRED_LEASE_SCRIPT,
        5,
        HEAVY_LEASE_KEY_PREFIX,
        HEAVY_PROCESSING_QUEUE_KEY,
        HEAVY_LEASE_EXPIRY_ZSET_KEY,
        HEAVY_QUEUE_KEY,
        "analysis:jobs",
        lease.token,
        str(lease.leased_at_ms),
        "drop",
        "1",
        "1",
        lease.priority,
    )
    return int(result) == 1
