"""add analysis job input payload storage key

Revision ID: 20260401_0038
Revises: 20260401_0037
Create Date: 2026-04-01 14:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260401_0038"
down_revision = "20260401_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column("input_payload_storage_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analysis_jobs", "input_payload_storage_key")
