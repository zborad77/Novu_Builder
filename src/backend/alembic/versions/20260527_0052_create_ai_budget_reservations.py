"""Create ai_budget_reservations — per-job reservation tracking for AI budget.

Problem solved:
    The running daily_tokens_used counter is updated atomically on reserve(),
    but if a worker process is killed hard (kill -9, OOM, power outage) between
    reserve() and release()/record_actual(), the reservation is never returned
    and tokens are silently leaked until the daily counter resets.

Solution:
    Track every reservation as a row with a status machine:
        reserved → consumed  (AI call completed successfully)
        reserved → released  (controlled failure — release path ran)
        reserved → expired   (sweeper picked up stale reservation after expiry)

    The sweeper runs periodically:
        WHERE status = 'reserved' AND reserved_at < now() - interval '15 minutes'
    and credits the tokens back to daily_tokens_used for each expired row.

Idempotency:
    UNIQUE(offer_job_id) prevents double-reserving the same job.
    Each retry creates a new OfferJob with a new id, so retries get
    fresh reservations.

Revision ID: 20260527_0052
Revises: 20260527_0051
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0052"
down_revision = "20260527_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_budget_reservations",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "offer_job_id",
            sa.String(64),
            sa.ForeignKey("offer_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="reserved",
        ),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_job_id", name="uq_ai_budget_res_job"),
        sa.CheckConstraint(
            "status IN ('reserved','consumed','released','expired')",
            name="ck_ai_budget_res_status",
        ),
        sa.CheckConstraint("token_estimate > 0", name="ck_ai_budget_res_estimate"),
    )
    op.create_index(
        "idx_ai_budget_res_stale",
        "ai_budget_reservations",
        ["status", "reserved_at"],
    )
    op.create_index(
        "idx_ai_budget_res_org",
        "ai_budget_reservations",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_budget_res_org", table_name="ai_budget_reservations")
    op.drop_index("idx_ai_budget_res_stale", table_name="ai_budget_reservations")
    op.drop_table("ai_budget_reservations")
