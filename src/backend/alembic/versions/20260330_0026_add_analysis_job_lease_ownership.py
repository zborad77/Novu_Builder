"""Add DB-backed analysis job lease ownership fields.

Revision ID: 20260330_0026
Revises: 20260330_0025
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0026"
down_revision = "20260330_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(sa.Column("lease_token", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("worker_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_column("heartbeat_at")
        batch_op.drop_column("leased_at")
        batch_op.drop_column("worker_id")
        batch_op.drop_column("lease_token")
