"""Harden offer pipeline — lease fencing token + SSE replay sequence.

Two additive columns:

offer_jobs.lease_version (INTEGER NOT NULL DEFAULT 0)
    Incremented atomically on every mark_job_running() call.
    Phase-3 persist checks WHERE lease_version = :expected before writing.
    A stale worker (lease expired, requeued, picked up by new worker) will
    see 0 rows updated and abort instead of overwriting the new worker's result.

outbox_events.seq (BIGINT GENERATED ALWAYS AS IDENTITY)
    Globally monotonic sequence for the outbox table.
    Published in every Redis SSE message so Qt clients can track their
    last-received event.  On reconnect, Qt sends Last-Event-ID: {seq} and
    the SSE endpoint replays any missed events from the DB before subscribing
    to Redis pub/sub — eliminating silent gaps across deploys and restarts.

Revision ID: 20260527_0051
Revises: 20260527_0050
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0051"
down_revision = "20260527_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Lease fencing token on offer_jobs --
    op.add_column(
        "offer_jobs",
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
    )

    # -- Monotonic sequence on outbox_events --
    # GENERATED ALWAYS AS IDENTITY: DB manages the sequence, application never
    # supplies a value.  Existing rows (if any) get sequential values assigned.
    op.execute(
        "ALTER TABLE outbox_events "
        "ADD COLUMN seq BIGINT GENERATED ALWAYS AS IDENTITY"
    )
    op.create_index(
        "idx_outbox_events_seq",
        "outbox_events",
        ["seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_events_seq", table_name="outbox_events")
    op.drop_column("outbox_events", "seq")
    op.drop_column("offer_jobs", "lease_version")
