"""Add hot-path indexes for tenant listings and analysis lookups.

Revision ID: 20260329_0023
Revises: 20260329_0022
Create Date: 2026-03-29
"""

from __future__ import annotations

from alembic import op


revision = "20260329_0023"
down_revision = "20260329_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_pricing_profiles_org_default_name",
        "pricing_profiles",
        ["organization_id", "is_default", "name"],
        unique=False,
    )
    op.create_index(
        "idx_material_catalog_org_active_name",
        "material_catalog",
        ["organization_id", "is_active", "name"],
        unique=False,
    )
    op.create_index(
        "idx_suppliers_org_active_name",
        "suppliers",
        ["organization_id", "is_active", "name"],
        unique=False,
    )
    op.create_index(
        "idx_analysis_jobs_project_status_created_id",
        "analysis_jobs",
        ["project_id", "status", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_analysis_jobs_project_created_id",
        "analysis_jobs",
        ["project_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_analysis_results_project_created_id",
        "analysis_results",
        ["project_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_analysis_results_job_created_id",
        "analysis_results",
        ["analysis_job_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_analysis_results_job_created_id", table_name="analysis_results")
    op.drop_index("idx_analysis_results_project_created_id", table_name="analysis_results")
    op.drop_index("idx_analysis_jobs_project_created_id", table_name="analysis_jobs")
    op.drop_index("idx_analysis_jobs_project_status_created_id", table_name="analysis_jobs")
    op.drop_index("idx_suppliers_org_active_name", table_name="suppliers")
    op.drop_index("idx_material_catalog_org_active_name", table_name="material_catalog")
    op.drop_index("idx_pricing_profiles_org_default_name", table_name="pricing_profiles")
