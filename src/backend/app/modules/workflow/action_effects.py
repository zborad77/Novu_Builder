"""Concrete transition side-effects, registered per status transition.

Načítá ho app.composition.wiring.init_modules() kvůli registraci efektů
(dekorátory plní registr v app.modules.cases.effects). Mimo modul workflow
se z něj nic neimportuje.

Transition -> effects map
-------------------------
intake -> analyzing
  before_commit  create AnalysisJob(status=queued)
  before_commit  write analysis.started OutboxEvent (SSE replay)
  after_commit   enqueue analysis queue payload so a worker can pick it up
  after_commit   publish analysis.started to Redis (live SSE delivery)

analyzing -> proposal_ready
  before_commit  write proposal.ready OutboxEvent (SSE replay)
  after_commit   publish proposal.ready to Redis (live SSE delivery)

proposal_ready -> quote_ready
  before_commit  mark all ProjectFinalProposals as approved (pricing lock)

quote_ready -> sent, sent -> archived
  efekty exportů vlastní modul exports (app/modules/exports/case_effects.py)
"""
from __future__ import annotations

from uuid import uuid4

import structlog
from sqlalchemy import update

from app.modules.cases.public import EffectContext, after_transition, before_transition
from app.platform.jobs.backpressure import analysis_job_priority_for_type
from app.platform.config import get_settings
from app.platform.events.types import (
    AGGREGATE_CASE,
    EVENT_ANALYSIS_STARTED,
    EVENT_PROPOSAL_READY,
    build_live_message,
)
from app.modules.analysis.public import AnalysisJob
from app.modules.quoting.public import ProjectFinalProposal
from app.modules.analysis.public import ANALYSIS_JOB_TYPE_MANUAL_TRIGGER
from app.platform.jobs.queue import enqueue_analysis_job

logger = structlog.get_logger(__name__)


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


@before_transition("intake", "analyzing")
async def _write_analysis_started_outbox(ctx: EffectContext) -> None:
    """Write analysis.started to the outbox in the same transaction as the status change."""
    from app.platform.events.outbox import build_case_activity_event
    event = build_case_activity_event(
        event_type=EVENT_ANALYSIS_STARTED,
        project_id=ctx.project.id,
        organization_id=ctx.project.organization_id,
        payload={"status": "analyzing"},
    )
    ctx.session.add(event)
    ctx.state["analysis_started_outbox_id"] = event.id


@after_transition("intake", "analyzing")
async def _publish_analysis_started_to_redis(ctx: EffectContext) -> None:
    """Publish analysis.started to Redis pub/sub for low-latency SSE delivery.

    Intentionally omits 'seq' — the outbox publisher owns that field.
    Clients deduplicate by 'event_id' (= outbox row id stored in ctx.state).
    """
    logger.info("domain_event.analysis_started", project_id=ctx.project.id)
    if ctx.work_queue is None:
        return
    outbox_id = ctx.state.get("analysis_started_outbox_id")
    message = build_live_message(
        event_id=outbox_id if isinstance(outbox_id, str) else str(uuid4()),
        event_type=EVENT_ANALYSIS_STARTED,
        aggregate_type=AGGREGATE_CASE,
        aggregate_id=ctx.project.id,
        payload={"status": "analyzing"},
    )
    await ctx.work_queue.publish(f"case:events:{ctx.project.id}", message)


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
        max_depth=settings.analysis_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=analysis_job_priority_for_type(ANALYSIS_JOB_TYPE_MANUAL_TRIGGER),
    )
    logger.info("analysis.job_transport_enqueued", project_id=ctx.project.id, job_id=job_id)


# ---------------------------------------------------------------------------
# worker_proposal_ready  —  analyzing → proposal_ready
# ---------------------------------------------------------------------------

@before_transition("analyzing", "proposal_ready")
async def _write_proposal_ready_outbox(ctx: EffectContext) -> None:
    """Write proposal.ready to the outbox in the same transaction as the status change."""
    from app.platform.events.outbox import build_case_activity_event
    event = build_case_activity_event(
        event_type=EVENT_PROPOSAL_READY,
        project_id=ctx.project.id,
        organization_id=ctx.project.organization_id,
        payload={"status": "proposal_ready"},
    )
    ctx.session.add(event)
    ctx.state["proposal_ready_outbox_id"] = event.id


@after_transition("analyzing", "proposal_ready")
async def _publish_proposal_ready_to_redis(ctx: EffectContext) -> None:
    """Publish proposal.ready to Redis pub/sub for low-latency SSE delivery.

    Omits 'seq' — the outbox publisher owns the monotonic sequence.
    Clients deduplicate by 'event_id'.
    """
    logger.info("domain_event.proposal_ready", project_id=ctx.project.id)
    if ctx.work_queue is None:
        return
    outbox_id = ctx.state.get("proposal_ready_outbox_id")
    message = build_live_message(
        event_id=outbox_id if isinstance(outbox_id, str) else str(uuid4()),
        event_type=EVENT_PROPOSAL_READY,
        aggregate_type=AGGREGATE_CASE,
        aggregate_id=ctx.project.id,
        payload={"status": "proposal_ready"},
    )
    await ctx.work_queue.publish(f"case:events:{ctx.project.id}", message)


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


# ---------------------------------------------------------------------------
# complete  —  sent → archived
# ---------------------------------------------------------------------------


