"""Add kind, proposal_step, geometry_correction_type, output_types to work_types;
add work_type_components table for composite type assembly.

kind                    — 'leaf' | 'composite'
proposal_step           — true when AI returns a proposal requiring explicit approval
                          before generating the final detailed solution (e.g. FVE layout)
geometry_correction_type — how raw measured area/length is corrected before pricing
output_types_json       — JSON array of analysis output types produced by this work type

work_type_components    — links composite work types to their leaf constituents

Revision ID: 20260417_0043
Revises: 20260416_0042
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260417_0043"
down_revision = "20260416_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extend work_types with kind, proposal_step, geometry_correction_type,
    # output_types_json
    # ------------------------------------------------------------------
    op.add_column(
        "work_types",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="leaf"),
    )
    op.add_column(
        "work_types",
        sa.Column("proposal_step", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "work_types",
        sa.Column(
            "geometry_correction_type",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "work_types",
        sa.Column("output_types_json", sa.Text(), nullable=True),
    )

    op.create_check_constraint(
        "ck_work_types_kind",
        "work_types",
        "kind IN ('leaf', 'composite')",
    )
    op.create_check_constraint(
        "ck_work_types_geometry_correction_type",
        "work_types",
        "geometry_correction_type IN ("
        "'none', 'slope_coefficient', 'net_from_gross', "
        "'pipe_length_from_drawing', 'volume_from_depth')",
    )
    op.create_index("idx_work_types_kind_state", "work_types", ["kind", "state", "code"])

    # ------------------------------------------------------------------
    # work_type_components — composite → leaf links
    # ------------------------------------------------------------------
    op.create_table(
        "work_type_components",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("parent_work_type_id", sa.String(length=64), nullable=False),
        sa.Column("component_work_type_id", sa.String(length=64), nullable=False),
        sa.Column("condition_code", sa.String(length=32), nullable=False, server_default="always"),
        sa.Column("quantity_multiplier", sa.Numeric(precision=14, scale=4), nullable=False, server_default="1.0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_work_type_id"],
            ["work_types.id"],
            ondelete="CASCADE",
            name="fk_work_type_components_parent",
        ),
        sa.ForeignKeyConstraint(
            ["component_work_type_id"],
            ["work_types.id"],
            ondelete="RESTRICT",
            name="fk_work_type_components_component",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_work_type_id",
            "component_work_type_id",
            name="uq_work_type_components_parent_component",
        ),
        sa.CheckConstraint(
            "condition_code IN ('always', 'if_detected', 'tenant_choice')",
            name="ck_work_type_components_condition_code",
        ),
        sa.CheckConstraint(
            "parent_work_type_id != component_work_type_id",
            name="ck_work_type_components_no_self_reference",
        ),
    )
    op.create_index(
        "idx_work_type_components_parent_sort",
        "work_type_components",
        ["parent_work_type_id", "sort_order", "component_work_type_id"],
    )
    op.create_index(
        "idx_work_type_components_component",
        "work_type_components",
        ["component_work_type_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_work_type_components_component", table_name="work_type_components")
    op.drop_index("idx_work_type_components_parent_sort", table_name="work_type_components")
    op.drop_table("work_type_components")

    op.drop_index("idx_work_types_kind_state", table_name="work_types")
    op.drop_constraint("ck_work_types_geometry_correction_type", "work_types", type_="check")
    op.drop_constraint("ck_work_types_kind", "work_types", type_="check")
    op.drop_column("work_types", "output_types_json")
    op.drop_column("work_types", "geometry_correction_type")
    op.drop_column("work_types", "proposal_step")
    op.drop_column("work_types", "kind")
