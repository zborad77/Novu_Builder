"""add analysis_result_id to project_final_proposals

Closes the measurement-lineage gap: every finalized proposal now records which
AnalysisResult fed its pricing.  Enables audit, replay, and diff explanation.

Revision ID: 20260527_0055
Revises: 20260527_0054
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260527_0055"
down_revision = "20260527_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_final_proposals",
        sa.Column(
            "analysis_result_id",
            sa.String(64),
            sa.ForeignKey("analysis_results.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_project_final_proposals_analysis_result_id",
        "project_final_proposals",
        ["analysis_result_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_project_final_proposals_analysis_result_id", table_name="project_final_proposals")
    op.drop_column("project_final_proposals", "analysis_result_id")
