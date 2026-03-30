"""Harden photo delete and export state machines.

Revision ID: 20260330_0025
Revises: 20260330_0024
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0025"
down_revision = "20260330_0024"
branch_labels = None
depends_on = None

_PHOTO_STATUS = "ck_project_photos_status"
_EXPORT_STATUS = "ck_project_exports_status"


def upgrade() -> None:
    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active")
        )
        batch_op.create_check_constraint(
            _PHOTO_STATUS,
            "status IN ('active', 'pending_delete', 'deleted')",
        )

    op.execute(
        """
        UPDATE project_exports
        SET status = 'completed'
        WHERE status NOT IN ('pending', 'generating', 'completed', 'failed')
        """
    )
    with op.batch_alter_table("project_exports") as batch_op:
        batch_op.create_check_constraint(
            _EXPORT_STATUS,
            "status IN ('pending', 'generating', 'completed', 'failed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_exports") as batch_op:
        batch_op.drop_constraint(_EXPORT_STATUS, type_="check")

    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.drop_constraint(_PHOTO_STATUS, type_="check")
        batch_op.drop_column("status")
