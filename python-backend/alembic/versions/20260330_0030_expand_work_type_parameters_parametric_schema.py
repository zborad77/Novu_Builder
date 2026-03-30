"""Expand work_type_parameters with parametric schema columns.

Adds five columns that make each parameter a self-describing specification
usable by API, UI, vision orchestration, and the pricing engine without
hard-coded branching by work-type code:

  section               — logical grouping for rendering / filtering
  min_number_value      — lower bound for number parameters (optional)
  max_number_value      — upper bound for number parameters (optional)
  vision_extractable    — true when an AI vision model can extract this field
  manual_override_allowed — false only for system-locked read-only fields

A compound index on (work_type_id, section, sort_order) enables section-scoped
rendering passes without loading the full parameter set.

Revision ID: 20260330_0030
Revises: 20260330_0029
Create Date: 2026-03-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260330_0030"
down_revision = "20260330_0029"
branch_labels = None
depends_on = None

_SECTION_CHECK = (
    "section IS NULL OR section IN ("
    "'dimensions', 'materials', 'condition_or_damage', "
    "'access_and_complexity', 'quantity_scope', 'optional_notes'"
    ")"
)


def upgrade() -> None:
    op.add_column(
        "work_type_parameters",
        sa.Column("section", sa.String(64), nullable=True),
    )
    op.add_column(
        "work_type_parameters",
        sa.Column("min_number_value", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "work_type_parameters",
        sa.Column("max_number_value", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "work_type_parameters",
        sa.Column(
            "vision_extractable",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "work_type_parameters",
        sa.Column(
            "manual_override_allowed",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.create_check_constraint(
        "ck_work_type_parameters_section",
        "work_type_parameters",
        _SECTION_CHECK,
    )
    op.create_index(
        "idx_work_type_parameters_section_sort",
        "work_type_parameters",
        ["work_type_id", "section", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_work_type_parameters_section_sort",
        table_name="work_type_parameters",
    )
    op.drop_constraint(
        "ck_work_type_parameters_section",
        "work_type_parameters",
        type_="check",
    )
    op.drop_column("work_type_parameters", "manual_override_allowed")
    op.drop_column("work_type_parameters", "vision_extractable")
    op.drop_column("work_type_parameters", "max_number_value")
    op.drop_column("work_type_parameters", "min_number_value")
    op.drop_column("work_type_parameters", "section")
