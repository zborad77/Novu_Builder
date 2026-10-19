"""Create offer_requests table — additive parallel path for AI offer pipeline.

Revision ID: 20260527_0046
Revises: 20260527_0045
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260527_0046"
down_revision = "20260527_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_requests",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(64), sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_by_user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("work_type_code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("photo_ids", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("auto_send", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_review_bypass", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("needs_more_info_payload", postgresql.JSONB(), nullable=True),
        sa.Column("result_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("client_version", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('submitted','queued','processing','needs_more_info','needs_review','completed','failed','cancelled')",
            name="ck_offer_requests_status",
        ),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_offer_requests_idempotency"),
    )
    op.create_index("idx_offer_requests_org_status", "offer_requests", ["organization_id", "status"])
    op.create_index("idx_offer_requests_org_created", "offer_requests", ["organization_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_offer_requests_org_created", table_name="offer_requests")
    op.drop_index("idx_offer_requests_org_status", table_name="offer_requests")
    op.drop_table("offer_requests")
