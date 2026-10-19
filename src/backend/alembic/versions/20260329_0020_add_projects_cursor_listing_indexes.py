"""add composite indexes for projects cursor-based listing

Revision ID: 20260329_0020
Revises: 20260329_0019
Create Date: 2026-03-29

WHY
---
ProjectRepository.list_projects issues:

    SELECT ... FROM projects
    WHERE  organization_id = :org          -- always present for tenant requests
    [AND   status = :status]               -- optional filter
    [AND   (created_at < :cursor_ts
            OR (created_at = :cursor_ts AND id < :cursor_id))]  -- cursor
    ORDER BY created_at DESC, id DESC
    LIMIT  N+1

The existing idx_projects_org_status covers (organization_id, status) as a
filter index, but it does NOT include the sort columns, so PostgreSQL performs
a full sort on the filtered rows after the index scan.

The two indexes added here let PostgreSQL satisfy both the equality filter
AND the ORDER BY from a single index scan — eliminating the sort step.

INDEX 1 — idx_projects_org_created_id
    (organization_id, created_at DESC, id DESC)
    Targets the common no-status path:
        WHERE organization_id = ?
        ORDER BY created_at DESC, id DESC

INDEX 2 — idx_projects_org_status_created_id
    (organization_id, status, created_at DESC, id DESC)
    Targets the status-filtered path:
        WHERE organization_id = ? AND status = ?
        ORDER BY created_at DESC, id DESC
    Justification: status has low cardinality (draft/active/completed/…);
    including it as the second column lets PostgreSQL skip entire status
    partitions and then traverse created_at in order — no sort needed.

The existing idx_projects_org_status (organization_id, status) is preserved;
it remains useful for pure-filter queries (e.g. COUNT(*)) that carry no
ORDER BY and do not benefit from the wider index.
"""
from alembic import op
from sqlalchemy import text

revision = "20260329_0020"
down_revision = "20260329_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Index 1: tenant-scoped cursor listing without status filter
    op.create_index(
        "idx_projects_org_created_id",
        "projects",
        ["organization_id", text("created_at DESC"), text("id DESC")],
    )

    # Index 2: tenant-scoped cursor listing with status filter
    op.create_index(
        "idx_projects_org_status_created_id",
        "projects",
        ["organization_id", "status", text("created_at DESC"), text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_projects_org_status_created_id", table_name="projects")
    op.drop_index("idx_projects_org_created_id", table_name="projects")
