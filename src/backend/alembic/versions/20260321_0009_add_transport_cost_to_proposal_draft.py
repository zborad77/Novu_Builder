"""add transport_cost to proposal draft

Revision ID: 20260321_0009
Revises: 20260321_0008
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20260321_0009"
down_revision = "20260321_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_proposal_drafts",
        sa.Column("transport_cost", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_proposal_drafts", "transport_cost")
