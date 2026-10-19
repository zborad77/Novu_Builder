"""Efekty přechodů zakázky vlastněné modulem exports (registrace v registru cases.effects).

quote_ready -> sent
  before_commit  create ProjectExport(quote-pdf, pending)
  after_commit   enqueue export_generate heavy-lane job

sent -> archived
  before_commit  create ProjectExport(case-zip, pending)
  after_commit   enqueue export_generate heavy-lane job

Modul načítá app.composition.wiring.init_modules(); pořadí efektů pro tyto
přechody je stejné jako dřív (jiný modul na ně efekty neregistruje).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import structlog

from app.modules.cases.effects import EffectContext, after_transition, before_transition
from app.platform.jobs.backpressure import heavy_job_priority_for_type
from app.platform.config import get_settings
from app.modules.exports.models import ProjectExport
from app.platform.jobs.heavy_queue import enqueue_heavy_job


logger = structlog.get_logger(__name__)

_EXPORT_TTL_DAYS = 30


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
        max_depth=settings.heavy_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=heavy_job_priority_for_type("export_generate"),
    )
    logger.info("quote.export_transport_enqueued", project_id=ctx.project.id, export_id=export_id)


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
        max_depth=settings.heavy_queue_max_depth,
        max_global_queued=settings.effective_backpressure_max_queued_jobs,
        priority=heavy_job_priority_for_type("export_generate"),
    )
    logger.info(
        "case.completion_export_transport_enqueued",
        project_id=ctx.project.id,
        export_id=export_id,
    )
