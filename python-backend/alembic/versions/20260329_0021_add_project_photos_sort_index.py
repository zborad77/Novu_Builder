"""add composite index on project_photos for sort-ordered listing

Revision ID: 20260329_0021
Revises: 20260329_0020
Create Date: 2026-03-29

WHY
---
PhotoRepository.list_photos_by_project_id issues:

    SELECT ... FROM project_photos
    WHERE   project_id = :project_id
    ORDER BY sort_order ASC, created_at ASC

The existing idx_project_photos_project_id covers the equality filter but does
not include the sort columns, so PostgreSQL must sort the filtered rows after
the index scan.

The composite index added here lets the planner satisfy both the equality
filter AND the ORDER BY from a single index scan — eliminating the sort step
for every photo listing call (list_photos, _ensure_analysis_reference,
clear_primary, clear_analysis_reference, move_photo).

INDEX — idx_project_photos_project_sort_created
    (project_id, sort_order ASC, created_at ASC)

    Covers:
        WHERE project_id = ?
        ORDER BY sort_order ASC, created_at ASC

    The leading project_id column satisfies the equality predicate; the planner
    then reads (sort_order, created_at) pairs in the required order with no
    additional sort.

EXISTING INDEX KEPT
    idx_project_photos_project_id (project_id) is preserved.
    The wider composite index logically makes it redundant for listing queries,
    but the single-column index may still be chosen by the planner for queries
    that do not carry an ORDER BY (e.g. COUNT, DELETE by project_id).
    Removing it is NOT done here — it is a separate, separately-validated step.
"""
from alembic import op

revision = "20260329_0021"
down_revision = "20260329_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_project_photos_project_sort_created",
        "project_photos",
        ["project_id", "sort_order", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_project_photos_project_sort_created",
        table_name="project_photos",
    )
