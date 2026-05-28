"""Create offer_jobs table — execution layer for offer processing.

Revision ID: 20260527_0047
Revises: 20260527_0046
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260527_0047"
down_revision = "20260527_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_jobs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("offer_request_id", sa.String(64), sa.ForeignKey("offer_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_detail", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_offer_jobs_status",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_offer_jobs_idempotency"),
    )
    op.create_index("idx_offer_jobs_request_status", "offer_jobs", ["offer_request_id", "status"])
    op.create_index("idx_offer_jobs_org_status", "offer_jobs", ["organization_id", "status"])
    op.create_index("idx_offer_jobs_next_retry", "offer_jobs", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("idx_offer_jobs_next_retry", table_name="offer_jobs")
    op.drop_index("idx_offer_jobs_org_status", table_name="offer_jobs")
    op.drop_index("idx_offer_jobs_request_status", table_name="offer_jobs")
    op.drop_table("offer_jobs")
