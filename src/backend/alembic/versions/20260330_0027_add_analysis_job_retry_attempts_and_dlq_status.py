"""Add analysis job attempt counter and dead-letter status.

Revision ID: 20260330_0027
Revises: 20260330_0026
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0027"
down_revision = "20260330_0026"
branch_labels = None
depends_on = None

_JOB_STATUS = "ck_analysis_jobs_status"


def upgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.drop_constraint(_JOB_STATUS, type_="check")
        batch_op.create_check_constraint(
            _JOB_STATUS,
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled', 'dead_letter')",
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_constraint(_JOB_STATUS, type_="check")
        batch_op.create_check_constraint(
            _JOB_STATUS,
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled')",
        )
        batch_op.drop_column("attempt_count")
