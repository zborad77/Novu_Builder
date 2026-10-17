"""Idempotent persist layer + poison job detection fields.

Two additions:

1. agent_runs: UNIQUE(offer_job_id)
   One job produces exactly one agent run. Without this constraint a stale
   worker could insert a second run for the same job (duplicate AI result).
   The fencing token prevents the stale worker from updating offer_jobs, but
   without this UNIQUE the second INSERT would still succeed silently and leave
   orphaned run rows that corrupt the audit trail.

2. offer_jobs.error_repeat_count (INTEGER NOT NULL DEFAULT 0)
   Counts consecutive failures with the same error_code.
   Used by the worker for poison job detection:
       if error_repeat_count >= POISON_THRESHOLD (3) and retryable:
           → skip remaining retries, move directly to failed / DLQ
   This prevents exponential retry storms from jobs with malformed input,
   unsupported image formats, or structurally invalid parameters that will
   never succeed regardless of how many times they are retried.

Revision ID: 20260527_0053
Revises: 20260527_0052
Create Date: 2026-05-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_0053"
down_revision = "20260527_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Idempotent persist: one job → at most one agent run --
    op.create_unique_constraint(
        "uq_agent_runs_offer_job",
        "agent_runs",
        ["offer_job_id"],
    )

    # -- Poison job detection counter --
    op.add_column(
        "offer_jobs",
        sa.Column(
            "error_repeat_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("offer_jobs", "error_repeat_count")
    op.drop_constraint("uq_agent_runs_offer_job", "agent_runs", type_="unique")
