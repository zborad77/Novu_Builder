"""Add DB-level dedup guard for active analysis jobs.

Revision ID: 20260421_0045
Revises: 20260417_0044
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260421_0045"
down_revision = "20260417_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_analysis_jobs_active_project_job_type",
        "analysis_jobs",
        ["project_id", "job_type"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_analysis_jobs_active_project_job_type", table_name="analysis_jobs")
