"""SSE streaming endpoint for real-time offer status updates.

Replay-safe delivery guarantee:
    1. Qt client connects: GET /offer-requests/{id}/events
    2. On reconnect, Qt sends:  Last-Event-ID: 481
    3. Server fetches outbox_events WHERE aggregate_type='offer_request'
         AND aggregate_id=id AND seq > 481
       and streams missed events first, before subscribing to Redis.
    4. Every outbox-sourced SSE frame carries: id: {seq}
       Live frames carry no id: line — client does not advance Last-Event-ID.

Deduplication responsibility: client MUST deduplicate by event_id field.

Canonical message shape — see app.core.events.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_org_id
from app.core.events import build_outbox_message, sse_id_from_message
from app.core.metrics import observe_sse_connection, observe_sse_reconnect
from app.db.session import AsyncSessionFactory, get_db_session
from app.offer_processing.service import OfferNotFoundError, OfferService
from app.schemas.auth import AuthUserRead

router = APIRouter(prefix="/offer-requests", tags=["offer-events"])

_HEARTBEAT_INTERVAL_S = 30
_CHANNEL_PREFIX = "offer:events:"


def _get_offer_service(session: AsyncSession = Depends(get_db_session)) -> OfferService:
    return OfferService(session)


@router.get(
    "/{offer_id}/events",
    summary="SSE stream — replay-safe real-time offer status updates",
    response_class=StreamingResponse,
)
async def stream_offer_events(
    offer_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(get_current_user),
    offer_svc: OfferService = Depends(_get_offer_service),
) -> StreamingResponse:
    """Open a Server-Sent Events stream for a single offer request.

    Send Last-Event-ID on reconnect to replay any missed events.
    """
    org_id = require_org_id(current_user)

    try:
        await offer_svc.get_offer_request(offer_id, organization_id=org_id)
    except OfferNotFoundError:
        raise HTTPException(status_code=404, detail=f"Offer request '{offer_id}' not found.")

    redis = getattr(request.app.state, "job_queue", None)
    if redis is None:
        raise HTTPException(
            status_code=503,
            detail="Real-time events unavailable (Redis not connected).",
        )

    last_event_id_raw = request.headers.get("Last-Event-ID") or request.headers.get("last-event-id")
    last_seq: int | None = None
    if last_event_id_raw:
        try:
            last_seq = int(last_event_id_raw.strip())
        except (ValueError, OverflowError):
            last_seq = None

    channel = f"{_CHANNEL_PREFIX}{offer_id}"

    async def _event_generator():
        observe_sse_connection("offer_request", entering=True)
        try:
            # ---------------------------------------------------------------
            # Phase 1: replay missed events from DB (before subscribing live)
            # ---------------------------------------------------------------
            if last_seq is not None:
                async with AsyncSessionFactory() as session:
                    rows = await session.execute(
                        text("""
                            SELECT id, seq, event_type, aggregate_type, aggregate_id,
                                   payload, created_at
                            FROM outbox_events
                            WHERE aggregate_type = 'offer_request'
                              AND aggregate_id = :offer_id
                              AND seq > :last_seq
                            ORDER BY seq ASC
                            LIMIT 500
                        """),
                        {"offer_id": offer_id, "last_seq": last_seq},
                    )
                    missed = rows.fetchall()

                observe_sse_reconnect("offer_request", replayed=len(missed))
                for row in missed:
                    if await request.is_disconnected():
                        return
                    data = build_outbox_message(row)
                    yield f"id: {row.seq}\ndata: {data}\n\n"

            # ---------------------------------------------------------------
            # Phase 2: live subscription via Redis pub/sub
            # ---------------------------------------------------------------
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            heartbeat_task = asyncio.create_task(_sleep(_HEARTBEAT_INTERVAL_S))
            try:
                while True:
                    if await request.is_disconnected():
                        break

                    if heartbeat_task.done():
                        yield ": heartbeat\n\n"
                        heartbeat_task = asyncio.create_task(_sleep(_HEARTBEAT_INTERVAL_S))

                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message is not None and message.get("type") == "message":
                        raw = message.get("data", b"")
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")

                        seq_val = sse_id_from_message(raw)
                        if seq_val:
                            yield f"id: {seq_val}\ndata: {raw}\n\n"
                        else:
                            yield f"data: {raw}\n\n"

            finally:
                heartbeat_task.cancel()
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
        finally:
            observe_sse_connection("offer_request", entering=False)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)
