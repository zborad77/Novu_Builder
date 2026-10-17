"""SSE streaming endpoint for real-time case activity updates.

Replay-safe delivery guarantee (mirrors offer_events.py):
    1. Qt/web client connects: GET /cases/{id}/activity/stream
    2. On reconnect, client sends: Last-Event-ID: 481
    3. Server fetches outbox_events WHERE aggregate_type='case'
         AND aggregate_id=id AND seq > 481, streams missed events first,
         then subscribes to Redis pub/sub.
    4. Every outbox-sourced SSE frame carries: id: {seq}
       Live frames carry no id: line — client does not advance Last-Event-ID.

Canonical message shape — see app.core.events.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_manager, resolve_org_id
from app.core.events import build_outbox_message, sse_id_from_message
from app.core.metrics import observe_sse_connection, observe_sse_reconnect
from app.db.session import AsyncSessionFactory, get_db_session
from app.repositories.project_repository import ProjectRepository
from app.schemas.auth import AuthUserRead

router = APIRouter(prefix="/cases", tags=["case-events"])

_HEARTBEAT_INTERVAL_S = 30
_CHANNEL_PREFIX = "case:events:"
_REPLAY_LIMIT = 500


def _get_project_repository(session: AsyncSession = Depends(get_db_session)) -> ProjectRepository:
    return ProjectRepository(session)


@router.get(
    "/{case_id}/activity/stream",
    summary="SSE stream — replay-safe real-time case activity updates",
    response_class=StreamingResponse,
)
async def stream_case_activity(
    case_id: str,
    request: Request,
    current_user: AuthUserRead = Depends(require_manager),
    repo: ProjectRepository = Depends(_get_project_repository),
) -> StreamingResponse:
    """Open a Server-Sent Events stream for a single case.

    Send Last-Event-ID on reconnect to replay any missed events.
    """
    org_id = resolve_org_id(current_user)

    project = await repo.get_project_lean(case_id, organization_id=org_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Case not found.")

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

    channel = f"{_CHANNEL_PREFIX}{case_id}"

    async def _event_generator():
        observe_sse_connection("case", entering=True)
        try:
            # -----------------------------------------------------------------
            # Phase 1: replay missed events from DB (before subscribing live)
            # -----------------------------------------------------------------
            if last_seq is not None:
                async with AsyncSessionFactory() as session:
                    rows = await session.execute(
                        text("""
                            SELECT id, seq, event_type, aggregate_type, aggregate_id,
                                   payload, created_at
                            FROM outbox_events
                            WHERE aggregate_type = 'case'
                              AND aggregate_id = :case_id
                              AND seq > :last_seq
                            ORDER BY seq ASC
                            LIMIT :limit
                        """),
                        {"case_id": case_id, "last_seq": last_seq, "limit": _REPLAY_LIMIT},
                    )
                    missed = rows.fetchall()

                observe_sse_reconnect("case", replayed=len(missed))
                for row in missed:
                    if await request.is_disconnected():
                        return
                    data = build_outbox_message(row)
                    yield f"id: {row.seq}\ndata: {data}\n\n"

            # -----------------------------------------------------------------
            # Phase 2: live subscription via Redis pub/sub
            # -----------------------------------------------------------------
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
                            # Live event (no seq yet) — emit without id: so
                            # Last-Event-ID is not advanced; outbox delivery
                            # will carry the authoritative seq shortly after.
                            yield f"data: {raw}\n\n"

            finally:
                heartbeat_task.cancel()
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
        finally:
            observe_sse_connection("case", entering=False)

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
