"""Add name_cs (Czech display name) to work_categories and work_types.

Revision ID: 20260527_0045
Revises: 20260417_0044
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260527_0045"
down_revision = "20260417_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "work_categories",
        sa.Column("name_cs", sa.String(255), nullable=True),
    )
    op.add_column(
        "work_types",
        sa.Column("name_cs", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_types", "name_cs")
    op.drop_column("work_categories", "name_cs")
