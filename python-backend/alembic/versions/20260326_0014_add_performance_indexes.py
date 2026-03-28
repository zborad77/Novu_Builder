"""add performance indexes for status, created_at, expires_at

Revision ID: 20260326_0014
Revises: 20260326_0013
Create Date: 2026-03-26
"""
from alembic import op

revision = "20260326_0014"
down_revision = "20260326_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # projects — most-used filters and sort columns
    op.create_index("idx_projects_org_status", "projects", ["organization_id", "status"])
    op.create_index("idx_projects_created_at", "projects", ["created_at"])
    op.create_index("idx_projects_updated_at", "projects", ["updated_at"])

    # analysis_jobs — health-check queries + per-project listing
    op.create_index("idx_analysis_jobs_status", "analysis_jobs", ["status"])
    op.create_index("idx_analysis_jobs_project_created", "analysis_jobs", ["project_id", "created_at"])

    # revoked_tokens — cleanup query deletes by expires_at
    op.create_index("idx_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_index("idx_analysis_jobs_project_created", table_name="analysis_jobs")
    op.drop_index("idx_analysis_jobs_status", table_name="analysis_jobs")
    op.drop_index("idx_projects_updated_at", table_name="projects")
    op.drop_index("idx_projects_created_at", table_name="projects")
    op.drop_index("idx_projects_org_status", table_name="projects")
