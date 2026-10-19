"""Add marker_source column to markers table.

marker_source encodes mutability intent ('user' = editable, 'ai' = immutable).
Admin/superadmin are not modelled as separate sources: role info lives on the
users row pointed to by created_by, so no data is duplicated here.

Revision ID: 20260416_0042
Revises: 20260416_0041
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260416_0042"
down_revision = "20260416_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "markers",
        sa.Column(
            "marker_source",
            sa.String(length=16),
            nullable=False,
            server_default="user",
        ),
    )
    op.create_check_constraint(
        "ck_markers_marker_source",
        "markers",
        "marker_source IN ('user', 'ai')",
    )
    op.create_index("idx_markers_case_source", "markers", ["case_id", "marker_source"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_markers_case_source", table_name="markers")
    op.drop_constraint("ck_markers_marker_source", "markers", type_="check")
    op.drop_column("markers", "marker_source")
