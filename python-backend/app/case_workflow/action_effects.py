"""Concrete transition side-effects, registered per status transition.

This module is imported by case_actions.py purely for its registration
side-effects (the decorators populate the effect registries in effects.py).
Nothing in this module should be imported directly outside of case_workflow/.

Transition -> effects map
-------------------------
intake -> analyzing
  before_commit  create AnalysisJob(status=queued)
  after_commit   enqueue analysis queue payload so a worker can pick it up

proposal_ready -> quote_ready
  before_commit  mark all ProjectFinalProposals as approved (pricing lock)

quote_ready -> sent
  before_commit  create ProjectExport(quote-pdf, pending)
  after_commit   enqueue export_generate heavy-lane job

sent -> archived
  before_commit  create ProjectExport(case-zip, pending)
  after_commit   enqueue export_generate heavy-lane job
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import structlog
from sqlalchemy import update

from app.case_workflow.effects import EffectContext, after_transition, before_transition
from app.core.backpressure import analysis_job_priority_for_type, heavy_job_priority_for_type
from app.core.config import get_settings
from app.models.domain import AnalysisJob, ProjectExport, ProjectFinalProposal
from app.repositories.analysis_repository import ANALYSIS_JOB_TYPE_MANUAL_TRIGGER
from app.worker.heavy_queue import enqueue_heavy_job
from app.worker.queue import enqueue_analysis_job

logger = structlog.get_logger(__name__)

_EXPORT_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# start_analysis  —  intake → analyzing
# ---------------------------------------------------------------------------

@before_transition("intake", "analyzing")
async def _create_analysis_job(ctx: EffectContext) -> None:
    """Create the authoritative queued AnalysisJob row inside the transition txn."""
    job = AnalysisJob(
        id=f"job_{uuid4().hex[:8]}",
        project_id=ctx.project.id,
        status="queued",
        job_type=ANALYSIS_JOB_TYPE_MANUAL_TRIGGER,
        requested_by_user_id=ctx.actor_user_id,
    )
    ctx.session.add(job)
    ctx.state["analysis_job_id"] = job.id
    logger.info("analysis.job_queued", project_id=ctx.project.id, job_id=job.id)


@after_transition("intake", "analyzing")
async def _enqueue_analysis_job(ctx: EffectContext) -> None:
    """Trigger the analysis worker only after the status+job row is durable."""
    job_id = ctx.state.get("analysis_job_id")
    if not isinstance(job_id, str) or not job_id:
        logger.warning(
            "analysis.job_enqueue_skipped",
            project_id=ctx.project.id,
            reason="missing_analysis_job_id",
        )
        return
    if ctx.work_queue is None:
        logger.warning(
            "analysis.job_enqueue_skipped",
            project_id=ctx.project.id,
            job_id=job_id,
            reason="queue_unavailable",
        )
        return

    settings = get_settings()
    await enqueue_analysis_job(
        ctx.work_queue,
        job_id=job_id,
        project_id=ctx.project.id,
        organization_id=ctx.organization_id,
        is_superadmin_context=ctx.is_superadmin_context,
        dispatch_name="analysis.enqueue",
        max_depth=settings.analysis_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=analysis_job_priority_for_type(ANALYSIS_JOB_TYPE_MANUAL_TRIGGER),
    )
    logger.info("analysis.job_transport_enqueued", project_id=ctx.project.id, job_id=job_id)


# ---------------------------------------------------------------------------
# approve_proposal  —  proposal_ready → quote_ready
# ---------------------------------------------------------------------------

@before_transition("proposal_ready", "quote_ready")
async def _lock_proposal_pricing(ctx: EffectContext) -> None:
    """Mark all proposal snapshots as approved — signals that pricing is locked.

    Uses a direct UPDATE so no relationship load is required.
    """
    await ctx.session.execute(
        update(ProjectFinalProposal)
        .where(ProjectFinalProposal.project_id == ctx.project.id)
        .values(status="approved")
    )
    logger.info("proposal.pricing_locked", project_id=ctx.project.id)


# ---------------------------------------------------------------------------
# send_quote  —  quote_ready → sent
# ---------------------------------------------------------------------------

@before_transition("quote_ready", "sent")
async def _create_quote_export(ctx: EffectContext) -> None:
    """Create the authoritative pending quote PDF export row."""
    export = ProjectExport(
        id=f"exp_{uuid4().hex[:8]}",
        project_id=ctx.project.id,
        export_type="quote-pdf",
        status="pending",
        file_name=f"quote-{ctx.project.id}.pdf",
        expires_at=datetime.now(timezone.utc) + timedelta(days=_EXPORT_TTL_DAYS),
    )
    ctx.session.add(export)
    ctx.state["quote_export_id"] = export.id
    logger.info("quote.export_queued", project_id=ctx.project.id, export_id=export.id)


@after_transition("quote_ready", "sent")
async def _enqueue_quote_export(ctx: EffectContext) -> None:
    """Trigger heavy-lane quote PDF generation once the transition commits."""
    export_id = ctx.state.get("quote_export_id")
    if not isinstance(export_id, str) or not export_id:
        logger.warning(
            "quote.export_enqueue_skipped",
            project_id=ctx.project.id,
            reason="missing_export_id",
        )
        return
    if ctx.work_queue is None:
        logger.warning(
            "quote.export_enqueue_skipped",
            project_id=ctx.project.id,
            export_id=export_id,
            reason="queue_unavailable",
        )
        return

    settings = get_settings()
    await enqueue_heavy_job(
        ctx.work_queue,
        job_type="export_generate",
        project_id=ctx.project.id,
        organization_id=ctx.organization_id,
        export_id=export_id,
        dispatch_name="export.enqueue",
        max_depth=settings.heavy_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=heavy_job_priority_for_type("export_generate"),
    )
    logger.info("quote.export_transport_enqueued", project_id=ctx.project.id, export_id=export_id)


# ---------------------------------------------------------------------------
# complete  —  sent → archived
# ---------------------------------------------------------------------------

@before_transition("sent", "archived")
async def _create_completion_export(ctx: EffectContext) -> None:
    """Create the authoritative post-completion export row."""
    export = ProjectExport(
        id=f"exp_{uuid4().hex[:8]}",
        project_id=ctx.project.id,
        export_type="case-zip",
        status="pending",
        file_name=f"case-{ctx.project.id}.zip",
        expires_at=datetime.now(timezone.utc) + timedelta(days=_EXPORT_TTL_DAYS),
    )
    ctx.session.add(export)
    ctx.state["completion_export_id"] = export.id
    logger.info("case.completion_export_queued", project_id=ctx.project.id, export_id=export.id)


@after_transition("sent", "archived")
async def _enqueue_completion_export(ctx: EffectContext) -> None:
    """Trigger heavy-lane completion export once the archive transition commits."""
    export_id = ctx.state.get("completion_export_id")
    if not isinstance(export_id, str) or not export_id:
        logger.warning(
            "case.completion_export_enqueue_skipped",
            project_id=ctx.project.id,
            reason="missing_export_id",
        )
        return
    if ctx.work_queue is None:
        logger.warning(
            "case.completion_export_enqueue_skipped",
            project_id=ctx.project.id,
            export_id=export_id,
            reason="queue_unavailable",
        )
        return

    settings = get_settings()
    await enqueue_heavy_job(
        ctx.work_queue,
        job_type="export_generate",
        project_id=ctx.project.id,
        organization_id=ctx.organization_id,
        export_id=export_id,
        dispatch_name="export.enqueue",
        max_depth=settings.heavy_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=heavy_job_priority_for_type("export_generate"),
    )
    logger.info(
        "case.completion_export_transport_enqueued",
        project_id=ctx.project.id,
        export_id=export_id,
    )
