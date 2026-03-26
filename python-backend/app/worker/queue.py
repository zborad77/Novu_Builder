"""Minimal Redis FIFO job queue for analysis jobs (R-19).

Uses a single Redis list: RPUSH to enqueue, BLPOP (worker) / LPOP (tests) to dequeue.
Each item is a JSON-encoded dict: job_id, project_id, organization_id, is_superadmin_context.

Callers that hold a Redis client enqueue with enqueue_analysis_job().
The worker process dequeues with dequeue_analysis_job().
"""
import json

from redis.asyncio import Redis

QUEUE_KEY = "analysis:jobs"


async def enqueue_analysis_job(
    redis: Redis,
    *,
    job_id: str,
    project_id: str,
    organization_id: str | None,
    is_superadmin_context: bool,
) -> None:
    """Push a job payload to the tail of the Redis queue."""
    payload = json.dumps({
        "job_id": job_id,
        "project_id": project_id,
        "organization_id": organization_id,
        "is_superadmin_context": is_superadmin_context,
    })
    await redis.rpush(QUEUE_KEY, payload)


async def dequeue_analysis_job(redis: Redis, *, timeout: int = 5) -> dict | None:
    """Block for up to `timeout` seconds and return the next job payload, or None."""
    result = await redis.blpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _key, raw = result
    return json.loads(raw)
