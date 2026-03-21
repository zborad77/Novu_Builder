"""add estimated_duration_days and labor_hours_total to analysis_results

Revision ID: 20260321_0008
Revises: 20260321_0007
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20260321_0008"
down_revision = "20260321_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_results", sa.Column("estimated_duration_days", sa.Float(), nullable=True))
    op.add_column("analysis_results", sa.Column("labor_hours_total", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_results", "labor_hours_total")
    op.drop_column("analysis_results", "estimated_duration_days")
