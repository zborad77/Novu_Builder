"""Create agent_runs table — immutable AI invocation log.

Revision ID: 20260527_0048
Revises: 20260527_0047
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260527_0048"
down_revision = "20260527_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("offer_job_id", sa.String(64), sa.ForeignKey("offer_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("offer_request_id", sa.String(64), sa.ForeignKey("offer_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("input_snapshot_key", sa.String(512), nullable=True),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=True),
        sa.Column("snapshot_version_context", postgresql.JSONB(), nullable=True),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("agent_model", sa.String(128), nullable=True),
        sa.Column("agent_model_build", sa.String(128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("raw_output", postgresql.JSONB(), nullable=True),
        sa.Column("parsed_output", postgresql.JSONB(), nullable=True),
        sa.Column("validation_errors", postgresql.JSONB(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "outcome IN ('offer_generated','insufficient_data','error','cancelled')",
            name="ck_agent_runs_outcome",
        ),
    )
    op.create_index("idx_agent_runs_job", "agent_runs", ["offer_job_id"])
    op.create_index("idx_agent_runs_request", "agent_runs", ["offer_request_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_runs_request", table_name="agent_runs")
    op.drop_index("idx_agent_runs_job", table_name="agent_runs")
    op.drop_table("agent_runs")
