"""Minimal Redis FIFO job queue for analysis jobs (R-19).

Uses a single Redis list: RPUSH to enqueue, BLPOP (worker) / LPOP (tests) to dequeue.
Each item is a JSON-encoded dict: job_id, project_id, organization_id, is_superadmin_context.

Callers that hold a Redis client enqueue with enqueue_analysis_job().
The worker process dequeues with dequeue_analysis_job().
"""
import json

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from redis.asyncio import Redis

QUEUE_KEY = "analysis:jobs"


class InvalidAnalysisJobPayloadError(ValueError):
    """Raised when a Redis queue item cannot be decoded into the expected payload."""


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


async def enqueue_analysis_job(
    redis: Redis,
    *,
    job_id: str,
    project_id: str,
    organization_id: str | None,
    is_superadmin_context: bool,
) -> None:
    """Push a job payload to the tail of the Redis queue."""
    payload = validate_analysis_job_payload(
        {
            "job_id": job_id,
            "project_id": project_id,
            "organization_id": organization_id,
            "is_superadmin_context": is_superadmin_context,
        }
    )
    raw = json.dumps(payload.model_dump())
    await redis.rpush(QUEUE_KEY, raw)


async def dequeue_analysis_job(redis: Redis, *, timeout: int = 5) -> dict | None:
    """Block for up to `timeout` seconds and return the next job payload, or None."""
    result = await redis.blpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _key, raw = result
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
