"""add retry/traceback/payload fields to analysis_jobs

Revision ID: 20260324_0011
Revises: 20260321_0010
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260324_0011"
down_revision = "20260321_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("parent_job_id", sa.String(64), nullable=True))
    op.add_column("analysis_jobs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analysis_jobs", sa.Column("error_traceback", sa.Text(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("input_payload", sa.Text(), nullable=True))
    op.add_column("analysis_jobs", sa.Column("output_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_jobs", "output_summary")
    op.drop_column("analysis_jobs", "input_payload")
    op.drop_column("analysis_jobs", "error_traceback")
    op.drop_column("analysis_jobs", "retry_count")
    op.drop_column("analysis_jobs", "parent_job_id")
