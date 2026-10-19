"""Add DB-level integrity guards for work catalog parameters and runtime values.

Revision ID: 20260330_0031
Revises: 20260330_0030
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op


revision = "20260330_0031"
down_revision = "20260330_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_work_type_parameters_number_bounds_order",
        "work_type_parameters",
        "min_number_value IS NULL OR max_number_value IS NULL OR min_number_value <= max_number_value",
    )
    op.create_check_constraint(
        "ck_work_type_parameters_single_default_value",
        "work_type_parameters",
        "(CASE WHEN default_text_value IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN default_number_value IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN default_boolean_value IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN default_option_code IS NOT NULL THEN 1 ELSE 0 END) <= 1",
    )
    op.create_check_constraint(
        "ck_work_type_parameters_default_text_type",
        "work_type_parameters",
        "data_type = 'text' OR default_text_value IS NULL",
    )
    op.create_check_constraint(
        "ck_work_type_parameters_default_number_type",
        "work_type_parameters",
        "data_type = 'number' OR (default_number_value IS NULL AND min_number_value IS NULL AND max_number_value IS NULL)",
    )
    op.create_check_constraint(
        "ck_work_type_parameters_default_boolean_type",
        "work_type_parameters",
        "data_type = 'boolean' OR default_boolean_value IS NULL",
    )
    op.create_check_constraint(
        "ck_work_type_parameters_default_option_type",
        "work_type_parameters",
        "data_type = 'option' OR default_option_code IS NULL",
    )

    op.create_index(
        "idx_project_work_item_values_parameter_lookup",
        "project_work_item_values",
        ["work_type_parameter_id", "resolved_parameter_code"],
    )
    op.create_check_constraint(
        "ck_project_work_item_values_data_type",
        "project_work_item_values",
        "resolved_data_type IN ('number', 'text', 'boolean', 'option')",
    )
    op.create_check_constraint(
        "ck_project_work_item_values_typed_value_shape",
        "project_work_item_values",
        "("
        "(resolved_data_type = 'text' AND value_text IS NOT NULL AND value_number IS NULL AND value_boolean IS NULL AND value_option_code IS NULL) OR "
        "(resolved_data_type = 'number' AND value_number IS NOT NULL AND value_text IS NULL AND value_boolean IS NULL AND value_option_code IS NULL) OR "
        "(resolved_data_type = 'boolean' AND value_boolean IS NOT NULL AND value_text IS NULL AND value_number IS NULL AND value_option_code IS NULL) OR "
        "(resolved_data_type = 'option' AND value_option_code IS NOT NULL AND value_text IS NULL AND value_number IS NULL AND value_boolean IS NULL)"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_project_work_item_values_typed_value_shape",
        "project_work_item_values",
        type_="check",
    )
    op.drop_constraint(
        "ck_project_work_item_values_data_type",
        "project_work_item_values",
        type_="check",
    )
    op.drop_index(
        "idx_project_work_item_values_parameter_lookup",
        table_name="project_work_item_values",
    )

    op.drop_constraint(
        "ck_work_type_parameters_default_option_type",
        "work_type_parameters",
        type_="check",
    )
    op.drop_constraint(
        "ck_work_type_parameters_default_boolean_type",
        "work_type_parameters",
        type_="check",
    )
    op.drop_constraint(
        "ck_work_type_parameters_default_number_type",
        "work_type_parameters",
        type_="check",
    )
    op.drop_constraint(
        "ck_work_type_parameters_default_text_type",
        "work_type_parameters",
        type_="check",
    )
    op.drop_constraint(
        "ck_work_type_parameters_single_default_value",
        "work_type_parameters",
        type_="check",
    )
    op.drop_constraint(
        "ck_work_type_parameters_number_bounds_order",
        "work_type_parameters",
        type_="check",
    )
