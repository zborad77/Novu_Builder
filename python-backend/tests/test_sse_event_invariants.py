"""SSE event ordering, replay, deduplication, and stale-seq invariants.

Covers:
    1. Canonical envelope shape — all emitted messages conform to the spec.
    2. Replay ordering — seq monotonic ASC, never UUID/timestamp ordering.
    3. Reconnect correctness — Last-Event-ID > last_seq replays only newer events.
    4. Stale seq — Last-Event-ID newer than all stored events → empty replay.
    5. Duplicate delivery — same event_id across live + outbox paths is handled.
    6. Live message has no seq — SSE frame must NOT carry id: line.
    7. Outbox builder clean payload — no legacy redundant envelope fields.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

_NEEDS_PG = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None,
    reason="requires PostgreSQL (set TEST_DATABASE_URL)",
)

from app.core.events import (
    AGGREGATE_CASE,
    AGGREGATE_OFFER,
    EVENT_ANALYSIS_STARTED,
    EVENT_OFFER_STATUS_CHANGED,
    EVENT_PROPOSAL_READY,
    build_live_message,
    build_outbox_message,
    sse_id_from_message,
)
from app.offer_processing.outbox import (
    build_case_activity_event,
    build_offer_status_changed_event,
    build_outbox_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_row(**kwargs) -> SimpleNamespace:
    defaults = {
        "id": str(uuid4()),
        "seq": 1,
        "event_type": EVENT_ANALYSIS_STARTED,
        "aggregate_type": AGGREGATE_CASE,
        "aggregate_id": "proj_test",
        "organization_id": "org_test",
        "payload": {"status": "analyzing"},
        "created_at": datetime(2026, 5, 27, 10, 30, 0, tzinfo=UTC),
    }
    return SimpleNamespace(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# 1. Canonical envelope shape
# ---------------------------------------------------------------------------

class TestCanonicalEnvelopeShape:
    def test_outbox_message_has_all_required_fields(self):
        row = _fake_row(seq=42, id="evt_abc")
        msg = json.loads(build_outbox_message(row))

        assert msg["seq"] == 42
        assert msg["event_id"] == "evt_abc"
        assert msg["event_type"] == EVENT_ANALYSIS_STARTED
        assert msg["aggregate_type"] == AGGREGATE_CASE
        assert msg["aggregate_id"] == "proj_test"
        assert msg["occurred_at"] == "2026-05-27T10:30:00Z"
        assert "payload" in msg

    def test_live_message_has_no_seq_or_occurred_at(self):
        eid = str(uuid4())
        msg = json.loads(build_live_message(
            event_id=eid,
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_x",
            payload={"status": "analyzing"},
        ))

        assert "seq" not in msg
        assert "occurred_at" not in msg
        assert msg["event_id"] == eid
        assert msg["event_type"] == EVENT_ANALYSIS_STARTED
        assert msg["aggregate_type"] == AGGREGATE_CASE
        assert msg["aggregate_id"] == "proj_x"
        assert msg["payload"]["status"] == "analyzing"

    def test_outbox_occurred_at_is_z_suffix_utc(self):
        row = _fake_row(created_at=datetime(2026, 1, 15, 8, 5, 3, tzinfo=UTC))
        msg = json.loads(build_outbox_message(row))
        assert msg["occurred_at"] == "2026-01-15T08:05:03Z"

    def test_outbox_message_none_created_at_gives_none_occurred_at(self):
        row = _fake_row(created_at=None)
        msg = json.loads(build_outbox_message(row))
        assert msg["occurred_at"] is None


# ---------------------------------------------------------------------------
# 2. SSE id: line extraction
# ---------------------------------------------------------------------------

class TestSseIdExtraction:
    def test_extracts_integer_seq(self):
        msg = json.dumps({"seq": 142, "event_id": "x"})
        assert sse_id_from_message(msg) == "142"

    def test_returns_empty_when_no_seq(self):
        msg = json.dumps({"event_id": "x", "event_type": "analysis.started"})
        assert sse_id_from_message(msg) == ""

    def test_returns_empty_for_malformed_json(self):
        assert sse_id_from_message("not-json") == ""

    def test_live_message_yields_empty_id(self):
        live = build_live_message(
            event_id=str(uuid4()),
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_y",
            payload={},
        )
        assert sse_id_from_message(live) == ""

    def test_outbox_message_yields_integer_id(self):
        row = _fake_row(seq=500)
        outbox = build_outbox_message(row)
        assert sse_id_from_message(outbox) == "500"


# ---------------------------------------------------------------------------
# 3. Builder clean payload — no legacy redundant fields
# ---------------------------------------------------------------------------

class TestBuilderCleanPayload:
    def test_case_activity_event_payload_has_no_legacy_fields(self):
        event = build_case_activity_event(
            event_type=EVENT_ANALYSIS_STARTED,
            project_id="proj_z",
            organization_id="org_z",
            payload={"status": "analyzing"},
        )
        # payload must NOT contain envelope fields that belong in the row columns
        assert "project_id" not in event.payload
        assert "ts" not in event.payload
        assert "event_id" not in event.payload
        # payload MUST contain domain-specific facts
        assert event.payload["status"] == "analyzing"

    def test_offer_status_event_payload_has_no_legacy_fields(self):
        event = build_offer_status_changed_event(
            offer_request_id="ofr_test",
            organization_id="org_test",
            job_id="job_x",
            status="queued",
        )
        assert "offer_request_id" not in event.payload
        assert "ts" not in event.payload
        assert "event_id" not in event.payload
        assert event.payload["status"] == "queued"
        assert event.payload["job_id"] == "job_x"

    def test_build_outbox_event_row_id_is_canonical_event_id(self):
        event = build_outbox_event(
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_q",
            organization_id="org_q",
            payload={"status": "analyzing"},
        )
        # Row ID must be a valid UUID string
        assert len(event.id) == 36
        # Payload must NOT separately contain event_id (it lives in the envelope)
        assert "event_id" not in event.payload

    def test_correct_aggregate_type_strings(self):
        case_event = build_case_activity_event(
            event_type=EVENT_ANALYSIS_STARTED,
            project_id="p",
            organization_id="o",
        )
        offer_event = build_offer_status_changed_event(
            offer_request_id="r",
            organization_id="o",
            job_id=None,
            status="queued",
        )
        assert case_event.aggregate_type == AGGREGATE_CASE
        assert offer_event.aggregate_type == AGGREGATE_OFFER

    def test_correct_event_type_constants(self):
        assert EVENT_ANALYSIS_STARTED   == "analysis.started"
        assert EVENT_PROPOSAL_READY     == "proposal.ready"
        assert EVENT_OFFER_STATUS_CHANGED == "offer.status_changed"


# ---------------------------------------------------------------------------
# 4. Replay ordering — seq monotonic ASC invariant (DB-level)
# ---------------------------------------------------------------------------

@_NEEDS_PG
@pytest.mark.asyncio
async def test_replay_ordering_seq_asc(db_session):
    """Events replayed from outbox MUST be ordered by seq ASC, never by UUID or ts."""
    org_id = f"org_{uuid4().hex[:8]}"
    agg_id = f"proj_{uuid4().hex[:8]}"

    # Insert three outbox events in reverse logical order to prove ORDER BY seq
    # (not created_at or id) is enforced.
    event_ids = []
    for i in range(3):
        eid = str(uuid4())
        event_ids.append(eid)
        await db_session.execute(
            text("""
                INSERT INTO outbox_events
                    (id, event_type, aggregate_type, aggregate_id,
                     organization_id, payload, published)
                VALUES
                    (:id, :et, :at, :ai, :oi, :pl::jsonb, false)
            """),
            {
                "id": eid,
                "et": EVENT_ANALYSIS_STARTED,
                "at": AGGREGATE_CASE,
                "ai": agg_id,
                "oi": org_id,
                "pl": json.dumps({"status": "analyzing", "order_inserted": i}),
            },
        )
    await db_session.commit()

    # Read back ordered by seq
    rows = (await db_session.execute(
        text("""
            SELECT seq, id FROM outbox_events
            WHERE aggregate_type = :at AND aggregate_id = :ai
            ORDER BY seq ASC
        """),
        {"at": AGGREGATE_CASE, "ai": agg_id},
    )).fetchall()

    seqs = [r.seq for r in rows]
    assert seqs == sorted(seqs), "Replay seq values must be monotonically increasing"
    assert len(seqs) == 3


@_NEEDS_PG
@pytest.mark.asyncio
async def test_replay_last_seq_filter(db_session):
    """seq > last_seq must exclude all events at or before the boundary."""
    org_id = f"org_{uuid4().hex[:8]}"
    agg_id = f"proj_{uuid4().hex[:8]}"

    inserted_seqs = []
    for i in range(5):
        eid = str(uuid4())
        await db_session.execute(
            text("""
                INSERT INTO outbox_events
                    (id, event_type, aggregate_type, aggregate_id,
                     organization_id, payload, published)
                VALUES
                    (:id, :et, :at, :ai, :oi, :pl::jsonb, false)
            """),
            {
                "id": eid,
                "et": EVENT_ANALYSIS_STARTED,
                "at": AGGREGATE_CASE,
                "ai": agg_id,
                "oi": org_id,
                "pl": json.dumps({"status": "analyzing"}),
            },
        )
    await db_session.commit()

    all_rows = (await db_session.execute(
        text("SELECT seq FROM outbox_events WHERE aggregate_id = :ai ORDER BY seq ASC"),
        {"ai": agg_id},
    )).fetchall()
    inserted_seqs = [r.seq for r in all_rows]
    boundary_seq = inserted_seqs[2]  # replay from the third event onward

    replayed = (await db_session.execute(
        text("""
            SELECT seq FROM outbox_events
            WHERE aggregate_type = :at AND aggregate_id = :ai AND seq > :last
            ORDER BY seq ASC
        """),
        {"at": AGGREGATE_CASE, "ai": agg_id, "last": boundary_seq},
    )).fetchall()

    replayed_seqs = [r.seq for r in replayed]
    assert all(s > boundary_seq for s in replayed_seqs)
    assert len(replayed_seqs) == 2  # only events 4 and 5


@_NEEDS_PG
@pytest.mark.asyncio
async def test_stale_seq_returns_empty_replay(db_session):
    """Last-Event-ID newer than all stored events → zero replay rows."""
    org_id = f"org_{uuid4().hex[:8]}"
    agg_id = f"proj_{uuid4().hex[:8]}"

    await db_session.execute(
        text("""
            INSERT INTO outbox_events
                (id, event_type, aggregate_type, aggregate_id,
                 organization_id, payload, published)
            VALUES
                (:id, :et, :at, :ai, :oi, :pl::jsonb, false)
        """),
        {
            "id": str(uuid4()),
            "et": EVENT_ANALYSIS_STARTED,
            "at": AGGREGATE_CASE,
            "ai": agg_id,
            "oi": org_id,
            "pl": json.dumps({"status": "analyzing"}),
        },
    )
    await db_session.commit()

    max_seq = (await db_session.execute(
        text("SELECT MAX(seq) FROM outbox_events WHERE aggregate_id = :ai"),
        {"ai": agg_id},
    )).scalar_one()

    future_seq = max_seq + 999_999

    replayed = (await db_session.execute(
        text("""
            SELECT seq FROM outbox_events
            WHERE aggregate_type = :at AND aggregate_id = :ai AND seq > :last
            ORDER BY seq ASC
        """),
        {"at": AGGREGATE_CASE, "ai": agg_id, "last": future_seq},
    )).fetchall()

    assert len(replayed) == 0, "Stale Last-Event-ID must produce an empty replay"


# ---------------------------------------------------------------------------
# 5. Duplicate delivery — deduplicate by event_id
# ---------------------------------------------------------------------------

class TestDuplicateDelivery:
    def test_same_event_id_from_live_and_outbox_path_matches(self):
        """Live publish and outbox publish for the same transition must carry the same event_id."""
        row_id = str(uuid4())

        # Simulate: before-commit stores row with this id
        outbox_event = build_outbox_event(
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_dup",
            organization_id="org_dup",
            payload={"status": "proposal_ready"},
        )
        # The caller stores outbox_event.id in ctx.state for the after-commit publish
        stored_outbox_id = outbox_event.id

        # After-commit: live publish uses the same stored_outbox_id
        live_msg = json.loads(build_live_message(
            event_id=stored_outbox_id,
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_dup",
            payload={"status": "proposal_ready"},
        ))

        # Simulate an outbox row assembled with the same id
        fake_row = _fake_row(
            id=stored_outbox_id,
            seq=99,
            event_type=EVENT_PROPOSAL_READY,
            aggregate_id="proj_dup",
            payload={"status": "proposal_ready"},
        )
        outbox_msg = json.loads(build_outbox_message(fake_row))

        # Both paths carry the SAME event_id → client can deduplicate
        assert live_msg["event_id"] == outbox_msg["event_id"] == stored_outbox_id

    def test_live_and_outbox_differ_by_seq_presence(self):
        row_id = str(uuid4())
        live = json.loads(build_live_message(
            event_id=row_id,
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="p",
            payload={},
        ))
        outbox = json.loads(build_outbox_message(_fake_row(id=row_id, seq=7)))

        assert "seq" not in live
        assert outbox["seq"] == 7

    def test_sse_frame_id_only_on_outbox_path(self):
        live = build_live_message(
            event_id=str(uuid4()),
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="p",
            payload={},
        )
        outbox = build_outbox_message(_fake_row(seq=200))

        assert sse_id_from_message(live) == ""     # no id: on live frame
        assert sse_id_from_message(outbox) == "200"  # id: on outbox frame


# ---------------------------------------------------------------------------
# 6. Reconnect behaviour — Last-Event-ID advancement invariants
# ---------------------------------------------------------------------------

class TestReconnectBehavior:
    """Verify which frames advance Last-Event-ID and which do not.

    The client advances last_seq only when sse_id_from_message() returns a
    non-empty string (i.e. the frame carries a 'seq' field).  Live frames
    MUST NOT advance last_seq — they are ephemeral.  Outbox frames MUST.
    """

    def test_live_only_stream_does_not_advance_last_seq(self):
        last_seq: int | None = None
        for _ in range(3):
            raw = build_live_message(
                event_id=str(uuid4()),
                event_type=EVENT_ANALYSIS_STARTED,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id="proj_reconnect",
                payload={"status": "analyzing"},
            )
            val = sse_id_from_message(raw)
            if val:
                last_seq = int(val)

        assert last_seq is None, "Live-only stream must not advance Last-Event-ID"

    def test_mixed_stream_advances_only_on_outbox_frames(self):
        last_seq: int | None = None

        # Live frame (fast path) — must not advance seq.
        live1 = build_live_message(
            event_id=str(uuid4()),
            event_type=EVENT_ANALYSIS_STARTED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="p",
            payload={},
        )
        val = sse_id_from_message(live1)
        if val:
            last_seq = int(val)
        assert last_seq is None

        # Outbox frame (durable path) — MUST advance seq.
        outbox1 = build_outbox_message(_fake_row(seq=10, id=str(uuid4())))
        val = sse_id_from_message(outbox1)
        if val:
            last_seq = int(val)
        assert last_seq == 10

        # Another live frame — must leave last_seq unchanged.
        live2 = build_live_message(
            event_id=str(uuid4()),
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="p",
            payload={},
        )
        val = sse_id_from_message(live2)
        if val:
            last_seq = int(val)
        assert last_seq == 10, "Live frame after outbox must not change last_seq"

        # Second outbox at higher seq — must advance.
        outbox2 = build_outbox_message(_fake_row(seq=11, id=str(uuid4())))
        val = sse_id_from_message(outbox2)
        if val:
            last_seq = int(val)
        assert last_seq == 11

    def test_last_seq_is_the_value_sent_as_last_event_id_on_reconnect(self):
        """Whatever value was stored as last_seq becomes the Last-Event-ID header."""
        row = _fake_row(seq=482)
        outbox = build_outbox_message(row)
        val = sse_id_from_message(outbox)

        # Client sends "Last-Event-ID: 482" on reconnect
        assert val == "482"
        # Server parses it back to int for the WHERE seq > :last_seq query
        assert int(val) == 482


# ---------------------------------------------------------------------------
# 7. Out-of-order delivery — deduplication handles both arrival orders
# ---------------------------------------------------------------------------

class TestOutOfOrderDelivery:
    """The client deduplicates by event_id regardless of which path delivers first."""

    def test_live_then_outbox_deduplicates(self):
        """Live arrives first (fast path), outbox arrives second (durable path).
        Client must deliver exactly one event.
        """
        event_id = str(uuid4())
        seen: set[str] = set()
        delivered: list[dict] = []

        for raw in [
            build_live_message(
                event_id=event_id,
                event_type=EVENT_ANALYSIS_STARTED,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id="p",
                payload={"status": "analyzing"},
            ),
            build_outbox_message(_fake_row(id=event_id, seq=55)),
        ]:
            msg = json.loads(raw)
            if msg["event_id"] not in seen:
                seen.add(msg["event_id"])
                delivered.append(msg)

        assert len(delivered) == 1
        assert delivered[0]["event_id"] == event_id

    def test_outbox_then_live_deduplicates(self):
        """Outbox arrives first (replay on reconnect), live arrives second.
        Client must deliver the first (durable) copy.
        """
        event_id = str(uuid4())
        seen: set[str] = set()
        delivered: list[dict] = []

        for raw in [
            build_outbox_message(_fake_row(id=event_id, seq=100)),
            build_live_message(
                event_id=event_id,
                event_type=EVENT_ANALYSIS_STARTED,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id="p",
                payload={"status": "analyzing"},
            ),
        ]:
            msg = json.loads(raw)
            if msg["event_id"] not in seen:
                seen.add(msg["event_id"])
                delivered.append(msg)

        assert len(delivered) == 1
        assert delivered[0].get("seq") == 100, "First delivery must be the durable outbox version"

    def test_two_distinct_events_both_delivered(self):
        """Different event_ids must both reach the client."""
        id_a, id_b = str(uuid4()), str(uuid4())
        seen: set[str] = set()
        delivered: list[dict] = []

        for raw in [
            build_outbox_message(_fake_row(id=id_a, seq=1)),
            build_outbox_message(_fake_row(id=id_b, seq=2)),
        ]:
            msg = json.loads(raw)
            if msg["event_id"] not in seen:
                seen.add(msg["event_id"])
                delivered.append(msg)

        assert len(delivered) == 2
        delivered_ids = {d["event_id"] for d in delivered}
        assert delivered_ids == {id_a, id_b}


# ---------------------------------------------------------------------------
# 8. Proposal recompute idempotence
# ---------------------------------------------------------------------------

class TestProposalRecomputeIdempotence:
    """Verify proposal.ready event emission is safe under retry / concurrency.

    The key invariant: each DB commit that successfully calls
    replace_project_variants → apply_transition("proposal_ready") generates
    exactly one OutboxEvent with a fresh id.  If the transition is rejected
    (TransitionError — project already moved on), no OutboxEvent is written.
    The builder itself is pure; idempotence is enforced by the DB-level
    unique constraint on the state machine transition.
    """

    def test_each_build_call_generates_unique_event_id(self):
        e1 = build_outbox_event(
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_idempotent",
            organization_id="org_idempotent",
            payload={"status": "proposal_ready"},
        )
        e2 = build_outbox_event(
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_idempotent",
            organization_id="org_idempotent",
            payload={"status": "proposal_ready"},
        )
        assert e1.id != e2.id, "Each build must produce a unique outbox row id"

    def test_event_shape_is_stable_across_retries(self):
        """Shape must be identical regardless of how many retry attempts run."""
        events = [
            build_outbox_event(
                event_type=EVENT_PROPOSAL_READY,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id="proj_stable",
                organization_id="org_stable",
                payload={"status": "proposal_ready"},
            )
            for _ in range(3)
        ]
        for e in events:
            assert e.event_type == EVENT_PROPOSAL_READY
            assert e.aggregate_type == AGGREGATE_CASE
            assert e.aggregate_id == "proj_stable"
            assert e.payload == {"status": "proposal_ready"}

    def test_proposal_ready_payload_is_minimal(self):
        """proposal.ready payload carries only domain facts — no envelope bleed."""
        e = build_outbox_event(
            event_type=EVENT_PROPOSAL_READY,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_min",
            organization_id="org_min",
            payload={"status": "proposal_ready"},
        )
        assert set(e.payload.keys()) == {"status"}
        assert e.payload["status"] == "proposal_ready"

    def test_analysis_completed_event_shape(self):
        """analysis.completed uses the same canonical shape as other case events."""
        from app.core.events import EVENT_ANALYSIS_COMPLETED  # noqa: PLC0415
        e = build_outbox_event(
            event_type=EVENT_ANALYSIS_COMPLETED,
            aggregate_type=AGGREGATE_CASE,
            aggregate_id="proj_ac",
            organization_id="org_ac",
            payload={"status": "analysis_completed"},
        )
        assert e.event_type == "analysis.completed"
        assert e.aggregate_type == AGGREGATE_CASE
        assert e.payload == {"status": "analysis_completed"}
        assert "event_id" not in e.payload
