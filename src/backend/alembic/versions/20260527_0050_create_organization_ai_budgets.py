"""Create organization_ai_budgets table — per-tenant cost governance.

Budget check must be atomic: UPDATE ... WHERE daily_tokens_used + :est <= limit.
This prevents race conditions where two concurrent requests both pass a
read-then-check pattern and together exceed the limit.

Revision ID: 20260527_0050
Revises: 20260527_0049
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260527_0050"
down_revision = "20260527_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_ai_budgets",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("daily_token_limit", sa.Integer(), nullable=False, server_default="200000"),
        sa.Column("monthly_cost_limit_usd", sa.Numeric(10, 2), nullable=False, server_default="500.00"),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("daily_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_cost_used_usd", sa.Numeric(10, 2), nullable=False, server_default="0.00"),
        sa.Column("daily_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_hard_limit", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_org_ai_budgets_org"),
        sa.CheckConstraint("daily_token_limit > 0", name="ck_org_ai_budgets_token_limit"),
        sa.CheckConstraint("alert_threshold_pct BETWEEN 1 AND 100", name="ck_org_ai_budgets_alert_pct"),
    )


def downgrade() -> None:
    op.drop_table("organization_ai_budgets")
