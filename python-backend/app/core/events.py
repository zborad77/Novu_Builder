"""Canonical event taxonomy and SSE message assembly.

Every SSE message — whether replayed from the outbox or published live to Redis —
MUST conform to the canonical envelope defined here.

Canonical envelope shape
------------------------
Outbox-sourced (seq known, full durability):
    {
        "seq":            142,
        "event_id":       "uuid-v4",          # outbox_events.id
        "event_type":     "analysis.started",
        "aggregate_type": "case",
        "aggregate_id":   "proj_abc123",
        "occurred_at":    "2026-05-27T10:30:00Z",  # outbox_events.created_at UTC
        "payload":        { ... }             # domain-specific facts only
    }

Live-sourced (published directly to Redis after commit, seq not yet available):
    {
        "event_id":       "uuid-v4",          # same as the outbox row id (pre-generated)
        "event_type":     "analysis.started",
        "aggregate_type": "case",
        "aggregate_id":   "proj_abc123",
        "payload":        { ... }
    }
    # No "seq" or "occurred_at" — added by the outbox publisher when it catches up.
    # Clients MUST NOT use live frames to advance Last-Event-ID.
    # Clients MUST deduplicate by event_id.

SSE frame layout
----------------
Outbox frame (from replay or outbox publisher):
    id: 142
    data: { ... canonical envelope with seq ... }

Live frame (direct Redis publish):
    data: { ... canonical envelope without seq ... }
    # No "id:" line → browser / QNetworkAccessManager does not advance Last-Event-ID.

Event type constants
--------------------
Always use these constants instead of bare strings to prevent typos and enable
grep-based cross-referencing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Case-level events  (aggregate_type = "case")
# ---------------------------------------------------------------------------

EVENT_ANALYSIS_STARTED             = "analysis.started"
EVENT_ANALYSIS_COMPLETED           = "analysis.completed"
EVENT_MEASUREMENT_CONFIRMED        = "measurement.confirmed"
EVENT_PROPOSAL_RECALCULATE_STARTED = "proposal.recalculate.started"
EVENT_PROPOSAL_READY               = "proposal.ready"
EVENT_QUOTE_READY                  = "quote.ready"
EVENT_EXPORT_COMPLETED             = "export.completed"

# ---------------------------------------------------------------------------
# Offer-level events  (aggregate_type = "offer_request")
# ---------------------------------------------------------------------------

EVENT_OFFER_STATUS_CHANGED = "offer.status_changed"

# ---------------------------------------------------------------------------
# Aggregate type strings
# ---------------------------------------------------------------------------

AGGREGATE_CASE         = "case"
AGGREGATE_OFFER        = "offer_request"

# ---------------------------------------------------------------------------
# Canonical message assembly
# ---------------------------------------------------------------------------


@runtime_checkable
class _OutboxRow(Protocol):
    """Structural interface for an outbox_events DB row returned by SQLAlchemy text()."""
    id: str
    seq: int
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict
    created_at: datetime | None


def _format_occurred_at(dt: datetime | None) -> str | None:
    """Return ISO-8601 UTC string with 'Z' suffix, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_outbox_message(row: _OutboxRow) -> str:
    """Assemble the canonical SSE payload from an outbox_events row.

    This is the authoritative representation for:
    - Outbox publisher (OutboxPublisher._publish_batch)
    - SSE replay phase in offer_events.py / case_events.py
    """
    return json.dumps({
        "seq":            row.seq,
        "event_id":       row.id,
        "event_type":     row.event_type,
        "aggregate_type": row.aggregate_type,
        "aggregate_id":   row.aggregate_id,
        "occurred_at":    _format_occurred_at(row.created_at),
        "payload":        row.payload,
    })


def build_live_message(
    *,
    event_id: str,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
) -> str:
    """Assemble the canonical SSE payload for a direct Redis publish.

    Used after a DB commit when seq/occurred_at are not yet known.
    The SSE generator will emit this frame WITHOUT an 'id:' line so
    the client does not advance Last-Event-ID.  The outbox publisher
    will later deliver the durable version with seq.
    """
    return json.dumps({
        "event_id":       event_id,
        "event_type":     event_type,
        "aggregate_type": aggregate_type,
        "aggregate_id":   aggregate_id,
        "payload":        payload,
    })


def sse_id_from_message(raw: str) -> str:
    """Extract the SSE frame id (seq) from a canonical message.  Returns '' if absent."""
    try:
        parsed = json.loads(raw)
        seq = parsed.get("seq")
        return str(seq) if seq is not None else ""
    except (json.JSONDecodeError, TypeError):
        return ""
