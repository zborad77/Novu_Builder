"""Redis-backed offer job queue with lease/ack semantics.

Mirrors the design of app/worker/queue.py (analysis queue) but uses a
dedicated namespace so the two lanes never interfere.

Three priority tiers — worker always drains high before normal before low:
    offer:high    — enterprise / SLA-sensitive
    offer:normal  — standard tier (default)
    offer:low     — background / free tier

Lease semantics:
    dequeue_offer_job() atomically moves the payload to the processing list
    and sets a Redis lease with expiry.  The reaper re-queues stale leases.
    Successful processing must ACK the lease.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from redis.asyncio import Redis
import structlog

# ---------------------------------------------------------------------------
# Queue key namespace
# ---------------------------------------------------------------------------

OFFER_QUEUE_HIGH    = "offer:high"
OFFER_QUEUE_NORMAL  = "offer:normal"
OFFER_QUEUE_LOW     = "offer:low"

OFFER_PROCESSING_KEY      = "offer:processing"
OFFER_LEASE_KEY_PREFIX    = "offer:lease:"
OFFER_LEASE_EXPIRY_KEY    = "offer:lease_expiry"
OFFER_LEASE_SEQUENCE_KEY  = "offer:lease_sequence"
OFFER_DLQ_PREFIX          = "offer:dlq:"
OFFER_DLQ_ACTIVE_SET_KEY  = "offer:dlq:active"

PRIORITY_HIGH   = "high"
PRIORITY_NORMAL = "normal"
PRIORITY_LOW    = "low"

OFFER_LEASE_TIMEOUT_MS = 5 * 60 * 1000   # 5 minutes

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Job payload
# ---------------------------------------------------------------------------


class OfferJobPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id:           str
    offer_request_id: str
    organization_id:  str
    work_type_code:   str
    idempotency_key:  str
    photo_ids:        list[str]
    parameters:       dict[str, Any]
    attempt:          int = 1
    priority:         str = PRIORITY_NORMAL

    @field_validator("priority")
    @classmethod
    def _valid_priority(cls, v: str) -> str:
        if v not in {PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW}:
            return PRIORITY_NORMAL
        return v

    @field_validator("work_type_code")
    @classmethod
    def _non_empty_code(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("work_type_code must not be empty")
        return v


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OfferQueueCapacityError(RuntimeError):
    pass


class OfferLeaseOwnershipError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Lua script: atomic lease (mirrors analysis queue design)
# ---------------------------------------------------------------------------

_LEASE_SCRIPT = """
local total_processing = redis.call('LLEN', KEYS[1])
if total_processing >= tonumber(ARGV[4]) then
    return {'__backpressure__', tostring(total_processing)}
end

-- Try queues in priority order: high → normal → low
local raw = nil
for i = 2, 4 do
    raw = redis.call('LPOP', KEYS[i])
    if raw then break end
end
if not raw then
    return nil
end

local token = tostring(redis.call('INCR', KEYS[5]))
local lease_key = KEYS[6] .. token
local leased_at_ms = ARGV[1]
local worker_id = ARGV[2]
local lease_timeout_ms = ARGV[3]
local expires_at_ms = tostring(tonumber(leased_at_ms) + tonumber(lease_timeout_ms))

redis.call('RPUSH', KEYS[1], raw)
redis.call('HSET', lease_key,
    'token', token,
    'raw', raw,
    'leased_at_ms', leased_at_ms,
    'worker_id', worker_id,
    'expires_at_ms', expires_at_ms
)
redis.call('ZADD', KEYS[7], expires_at_ms, token)
return {token, raw}
"""

_ACK_SCRIPT = """
local lease_key = KEYS[1] .. ARGV[1]
local exists = redis.call('EXISTS', lease_key)
if exists == 0 then return 0 end
local worker_id = redis.call('HGET', lease_key, 'worker_id')
if worker_id ~= ARGV[2] then return -1 end
local raw = redis.call('HGET', lease_key, 'raw')
redis.call('LREM', KEYS[2], 1, raw)
redis.call('DEL', lease_key)
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
"""


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------


async def enqueue_offer_job(
    redis: Redis,
    *,
    payload: OfferJobPayload,
    max_depth: int = 5_000,
) -> None:
    queue_key = _priority_queue_key(payload.priority)
    depth = await redis.llen(queue_key)
    if depth >= max_depth:
        raise OfferQueueCapacityError(
            f"Offer queue '{payload.priority}' is full ({depth}/{max_depth})."
        )
    raw = payload.model_dump_json()
    await redis.rpush(queue_key, raw)
    logger.debug(
        "offer_queue.enqueued",
        job_id=payload.job_id,
        offer_request_id=payload.offer_request_id,
        priority=payload.priority,
    )


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


@dataclass
class DequeuedOfferJob:
    lease_token: str
    payload: OfferJobPayload
    leased_at: datetime


async def dequeue_offer_job(
    redis: Redis,
    *,
    worker_id: str,
    max_concurrent: int = 10,
) -> DequeuedOfferJob | None:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)

    result = await redis.eval(
        _LEASE_SCRIPT,
        7,
        OFFER_PROCESSING_KEY,
        OFFER_QUEUE_HIGH,
        OFFER_QUEUE_NORMAL,
        OFFER_QUEUE_LOW,
        OFFER_LEASE_SEQUENCE_KEY,
        OFFER_LEASE_KEY_PREFIX,
        OFFER_LEASE_EXPIRY_KEY,
        str(now_ms),
        worker_id,
        str(OFFER_LEASE_TIMEOUT_MS),
        str(max_concurrent),
    )

    if result is None:
        return None

    token_b, raw_b = result
    if token_b == b"__backpressure__":
        return None

    token = token_b.decode() if isinstance(token_b, bytes) else str(token_b)
    raw = raw_b.decode() if isinstance(raw_b, bytes) else str(raw_b)

    try:
        payload = OfferJobPayload.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.error("offer_queue.invalid_payload", error=str(exc), raw=raw[:200])
        await _move_to_dlq(redis, raw, reason="invalid_payload")
        return None

    return DequeuedOfferJob(
        lease_token=token,
        payload=payload,
        leased_at=datetime.now(UTC),
    )


async def ack_offer_job(
    redis: Redis,
    *,
    lease_token: str,
    worker_id: str,
) -> None:
    result = await redis.eval(
        _ACK_SCRIPT,
        3,
        OFFER_LEASE_KEY_PREFIX,
        OFFER_PROCESSING_KEY,
        OFFER_LEASE_EXPIRY_KEY,
        lease_token,
        worker_id,
    )
    if result == -1:
        raise OfferLeaseOwnershipError(
            f"Worker {worker_id} does not own lease {lease_token}."
        )


async def get_offer_queue_counts(redis: Redis) -> tuple[int, int]:
    high = await redis.llen(OFFER_QUEUE_HIGH)
    normal = await redis.llen(OFFER_QUEUE_NORMAL)
    low = await redis.llen(OFFER_QUEUE_LOW)
    processing = await redis.llen(OFFER_PROCESSING_KEY)
    return (high + normal + low, processing)


async def _move_to_dlq(redis: Redis, raw: str, *, reason: str) -> None:
    import time  # noqa: PLC0415
    dlq_key = f"{OFFER_DLQ_PREFIX}{int(time.time())}"
    await redis.hset(dlq_key, mapping={"raw": raw, "reason": reason, "ts": str(time.time())})
    await redis.sadd(OFFER_DLQ_ACTIVE_SET_KEY, dlq_key)


def _priority_queue_key(priority: str) -> str:
    if priority == PRIORITY_HIGH:
        return OFFER_QUEUE_HIGH
    if priority == PRIORITY_LOW:
        return OFFER_QUEUE_LOW
    return OFFER_QUEUE_NORMAL
