"""Create reconciler_events audit log table.

Stores a permanent, queryable record of every action the OfferReconciler takes.
Structlog captures the same data operationally; this table enables:
  - per-request reconciliation history  (support debugging, SLA analysis)
  - per-check-type frequency analytics  (track systemic failure patterns)
  - per-org breakdown                   (identify problematic tenants)

check_type values:
    expired_lease   — a running job's lease expired without an ACK
    stuck_request   — offer_request was queued/processing with no active job
    stale_outbox    — unpublished outbox events older than threshold

outcome values:
    requeued            — expired_lease: re-enqueued to Redis for retry
    failed_permanently  — expired_lease: retries exhausted, marked failed
    reconciled          — stuck_request: status aligned with latest job
    alert               — stale_outbox: count exceeded threshold (no DB change)

Note: no FK constraints on offer_job_id / offer_request_id — these are audit
rows and must survive even if the parent rows are deleted.

Revision ID: 20260527_0054
Revises: 20260527_0053
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260527_0054"
down_revision = "20260527_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciler_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("check_type", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(64), nullable=False),
        # Nullable — stale_outbox rows have no associated job/request
        sa.Column("offer_job_id", sa.String(64), nullable=True),
        sa.Column("offer_request_id", sa.String(64), nullable=True),
        sa.Column("organization_id", sa.String(64), nullable=True),
        sa.Column("old_status", sa.String(32), nullable=True),
        sa.Column("new_status", sa.String(32), nullable=True),
        sa.Column("reason", sa.String(128), nullable=True),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "check_type IN ('expired_lease','stuck_request','stale_outbox')",
            name="ck_reconciler_events_check_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('requeued','failed_permanently','reconciled','alert')",
            name="ck_reconciler_events_outcome",
        ),
    )

    op.create_index(
        "idx_reconciler_events_request",
        "reconciler_events",
        ["offer_request_id", "created_at"],
    )
    op.create_index(
        "idx_reconciler_events_check_type",
        "reconciler_events",
        ["check_type", "created_at"],
    )
    op.create_index(
        "idx_reconciler_events_org",
        "reconciler_events",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_reconciler_events_org", table_name="reconciler_events")
    op.drop_index("idx_reconciler_events_check_type", table_name="reconciler_events")
    op.drop_index("idx_reconciler_events_request", table_name="reconciler_events")
    op.drop_table("reconciler_events")
