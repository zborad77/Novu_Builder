"""C3: Add CHECK constraints for status columns.

Revision ID: 20260326_0016
Revises: 20260326_0015
Create Date: 2026-03-26

Adds DB-level CHECK constraints to status columns so invalid values are
rejected at the database layer. PostgreSQL enforces these; SQLite parses
but does not enforce them (dev parity is handled by application-layer
validation).

Status domains:
  projects.status              — draft | analysed | quoted | sent | archived
  project_photos.processing_status — uploaded | processing | ready | failed
  analysis_jobs.status         — queued | running | completed | failed | canceled
  project_final_proposals.status — ready_for_export | sent
"""
from alembic import op

revision = "20260326_0016"
down_revision = "20260326_0015"
branch_labels = None
depends_on = None

_PROJECT_STATUS = "ck_projects_status"
_PHOTO_PROC_STATUS = "ck_project_photos_processing_status"
_JOB_STATUS = "ck_analysis_jobs_status"
_PROPOSAL_STATUS = "ck_project_final_proposals_status"


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_check_constraint(
            _PROJECT_STATUS,
            "status IN ('draft', 'analysed', 'quoted', 'sent', 'archived')",
        )

    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.create_check_constraint(
            _PHOTO_PROC_STATUS,
            "processing_status IN ('uploaded', 'processing', 'ready', 'failed')",
        )

    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.create_check_constraint(
            _JOB_STATUS,
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled')",
        )

    with op.batch_alter_table("project_final_proposals") as batch_op:
        batch_op.create_check_constraint(
            _PROPOSAL_STATUS,
            "status IN ('ready_for_export', 'sent')",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_final_proposals") as batch_op:
        batch_op.drop_constraint(_PROPOSAL_STATUS, type_="check")

    with op.batch_alter_table("analysis_jobs") as batch_op:
        batch_op.drop_constraint(_JOB_STATUS, type_="check")

    with op.batch_alter_table("project_photos") as batch_op:
        batch_op.drop_constraint(_PHOTO_PROC_STATUS, type_="check")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_constraint(_PROJECT_STATUS, type_="check")
