"""Project status state machine: CheckConstraint, audit index, status_changed_*
columns, and project_status_history table.

Status values: draft | intake | analyzing | proposal_ready | quote_ready | sent |
               archived | cancelled

Locked statuses (photo uploads / edits rejected):
    analyzing, proposal_ready, quote_ready, sent

Terminal statuses: archived, cancelled

Revision ID: 20260417_0044
Revises: 20260417_0043
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260417_0044"
down_revision = "20260417_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # projects — add CheckConstraint + audit index + two new columns
    # ------------------------------------------------------------------
    op.add_column(
        "projects",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "status_changed_by_user_id",
            sa.String(length=64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Replace the old constraint (created in 20260326_0016) that only allowed
    # the legacy status set ('draft','analysed','quoted','sent','archived').
    op.drop_constraint("ck_projects_status", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_status",
        "projects",
        "status IN ("
        "'draft','intake','analyzing','proposal_ready',"
        "'quote_ready','sent','archived','cancelled')",
    )
    op.create_index("idx_projects_org_status", "projects", ["organization_id", "status"])

    # ------------------------------------------------------------------
    # project_status_history — immutable audit trail
    # ------------------------------------------------------------------
    op.create_table(
        "project_status_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=64), nullable=True),
        sa.Column("to_status", sa.String(length=64), nullable=False),
        sa.Column("transitioned_by_user_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "transitioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_psh_project",
        ),
        sa.ForeignKeyConstraint(
            ["transitioned_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_psh_user",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_psh_project_transitioned",
        "project_status_history",
        ["project_id", "transitioned_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_psh_project_transitioned", table_name="project_status_history")
    op.drop_table("project_status_history")

    op.drop_index("idx_projects_org_status", table_name="projects")
    # Restore the original constraint from 20260326_0016
    op.drop_constraint("ck_projects_status", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_status",
        "projects",
        "status IN ('draft', 'analysed', 'quoted', 'sent', 'archived')",
    )
    op.drop_column("projects", "status_changed_by_user_id")
    op.drop_column("projects", "status_changed_at")
