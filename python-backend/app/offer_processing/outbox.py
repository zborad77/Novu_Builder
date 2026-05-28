"""Transactional Outbox pattern for reliable SSE event delivery.

Problem without outbox:
    worker updates DB → publishes to Redis pub/sub
    If Redis publish fails after DB commit: SSE client never gets the event.
    If worker crashes between the two operations: same result.

Solution (Transactional Outbox):
    1. Writer: in the SAME transaction as the state change, INSERT into outbox_events.
    2. Publisher (background loop): reads unpublished events, pushes to Redis, marks published.

Guarantee: at-least-once delivery.
SSE consumers MUST deduplicate by event_id (= outbox_events.id, the row UUID).

Canonical message shape — see app.core.events for the full specification.
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    AGGREGATE_CASE,
    AGGREGATE_OFFER,
    EVENT_OFFER_STATUS_CHANGED,
    build_outbox_message,
)
from app.models.offer_processing import OutboxEvent

logger = structlog.get_logger(__name__)

# How many unpublished events to process per batch
_BATCH_SIZE = 50

# Redis channel prefixes by aggregate_type
_CHANNEL_PREFIX_BY_AGGREGATE_TYPE: dict[str, str] = {
    AGGREGATE_OFFER: "offer:events:",
    AGGREGATE_CASE:  "case:events:",
}
_OFFER_CHANNEL_PREFIX = "offer:events:"  # kept for backwards-compat import


def _channel_for_event(aggregate_type: str, aggregate_id: str) -> str:
    prefix = _CHANNEL_PREFIX_BY_AGGREGATE_TYPE.get(aggregate_type, f"events:{aggregate_type}:")
    return f"{prefix}{aggregate_id}"


# ---------------------------------------------------------------------------
# Writer — called within the same transaction as state changes
# ---------------------------------------------------------------------------


def build_outbox_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    organization_id: str,
    payload: dict[str, Any],
) -> OutboxEvent:
    """Build an OutboxEvent ready to be added to the current DB session.

    Call session.add(event) WITHIN the same transaction as the state change.
    The returned event's .id is the canonical event_id for deduplication.
    """
    return OutboxEvent(
        id=str(uuid4()),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        organization_id=organization_id,
        payload=payload,
    )


def build_case_activity_event(
    *,
    event_type: str,
    project_id: str,
    organization_id: str,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    """Convenience builder for case workflow activity events."""
    return build_outbox_event(
        event_type=event_type,
        aggregate_type=AGGREGATE_CASE,
        aggregate_id=project_id,
        organization_id=organization_id,
        payload=payload or {},
    )


def build_offer_status_changed_event(
    *,
    offer_request_id: str,
    organization_id: str,
    job_id: str | None,
    status: str,
    extra: dict[str, Any] | None = None,
) -> OutboxEvent:
    """Convenience builder for offer status change events."""
    return build_outbox_event(
        event_type=EVENT_OFFER_STATUS_CHANGED,
        aggregate_type=AGGREGATE_OFFER,
        aggregate_id=offer_request_id,
        organization_id=organization_id,
        payload={
            "status": status,
            "job_id": job_id,
            **(extra or {}),
        },
    )


# ---------------------------------------------------------------------------
# Publisher — background loop that reads outbox and pushes to Redis
# ---------------------------------------------------------------------------


class OutboxPublisher:
    """Background process that publishes outbox events to Redis pub/sub.

    Run as a background task within the offer worker process.
    Poll interval is short (default 200ms) to minimize SSE delivery latency.
    """

    def __init__(self, session_factory, redis, poll_interval_s: float = 0.2) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._poll_interval_s = poll_interval_s
        self._running = False
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()
        logger.info("outbox_publisher.started")
        while self._running:
            try:
                published = await self._publish_batch()
                if published == 0:
                    await self._sleep(self._poll_interval_s)
            except Exception:
                logger.exception("outbox_publisher.error")
                await self._sleep(1.0)

    def stop(self) -> None:
        self._running = False
        if self._stop_event is not None:
            self._stop_event.set()
        logger.info("outbox_publisher.stopped")

    async def _sleep(self, seconds: float) -> None:
        """Sleep for `seconds`, but wake immediately when stop() is called."""
        if self._stop_event is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _publish_batch(self) -> int:
        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT id, seq, event_type, aggregate_type, aggregate_id,
                           organization_id, payload, created_at
                    FROM outbox_events
                    WHERE published = false
                    ORDER BY seq ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                """),
                {"limit": _BATCH_SIZE},
            )
            events = rows.fetchall()
            if not events:
                return 0

            published_ids = []
            for row in events:
                channel = _channel_for_event(row.aggregate_type, row.aggregate_id)
                message = build_outbox_message(row)
                try:
                    await self._redis.publish(channel, message)
                    published_ids.append(row.id)
                except Exception:
                    logger.exception(
                        "outbox_publisher.redis_publish_failed",
                        event_id=row.id,
                        seq=row.seq,
                        channel=channel,
                    )

            if published_ids:
                await session.execute(
                    text("""
                        UPDATE outbox_events
                        SET published = true, published_at = now()
                        WHERE id = ANY(:ids)
                    """),
                    {"ids": published_ids},
                )
                await session.commit()

            published_rows = [r for r in events if r.id in set(published_ids)]
            if published_rows:
                try:
                    from app.core.metrics import observe_outbox_batch  # noqa: PLC0415
                    observe_outbox_batch(rows=published_rows)
                except Exception:
                    pass

            return len(published_ids)
