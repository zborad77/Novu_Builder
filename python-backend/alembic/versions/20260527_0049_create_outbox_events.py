"""Create outbox_events table — transactional outbox for reliable SSE delivery.

Events are written in the same transaction as state changes.
A background publisher reads unpublished events and pushes to Redis pub/sub.
SSE consumers deduplicate by event id.

Revision ID: 20260527_0049
Revises: 20260527_0048
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260527_0049"
down_revision = "20260527_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_outbox_events_unpublished", "outbox_events", ["published", "created_at"])
    op.create_index("idx_outbox_events_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])


def downgrade() -> None:
    op.drop_index("idx_outbox_events_aggregate", table_name="outbox_events")
    op.drop_index("idx_outbox_events_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
