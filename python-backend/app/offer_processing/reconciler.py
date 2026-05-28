"""Offer pipeline reconciliation sweeper.

Periodically finds and repairs inconsistent state left by:
    - kill -9 / OOM kill (worker died mid-job, lease not released)
    - Redis restart (job removed from processing list, DB still shows 'running')
    - Network partition (worker lost DB connection after AI call)
    - Bug in state transition (offer_request stuck in processing, no active job)
    - Outbox publisher lag (unpublished SSE events accumulating)

Design:
    - Two independent loops running at different cadences:

      Fast loop  (FAST_INTERVAL_S  = 60 s)
        - expired_leases:   running jobs whose lease expired → re-queue or fail
        - stuck_requests:   queued/processing requests with no active job → align

      Slow loop  (SLOW_INTERVAL_S = 600 s)
        - stale_outbox:     unpublished events older than threshold → alert

    - Each check uses FOR UPDATE SKIP LOCKED — concurrent reconciler instances
      will not interfere with each other or with live workers
    - Incrementing lease_version on re-queue invalidates any zombie worker
      that wakes up and attempts Phase-3 persist (fencing check → abort)
    - Budget reservations are handled separately by BudgetSweeper
    - stop() wakes both sleeping loops immediately (interruptible sleep)

Checks (in order of severity):

1. expired_leases
   offer_jobs WHERE status='running' AND leased_until < now() - GRACE
   → re-queue OR fail (if retries exhausted)
   → increment lease_version to fence zombie workers
   → re-enqueue to Redis

2. stuck_requests
   offer_requests WHERE status IN ('queued','processing')
                   AND updated_at < now() - STUCK_THRESHOLD
                   AND no active offer_jobs (queued/running)
   → align offer_request status with the terminal state of its latest job
   → or mark as failed if no jobs exist at all (data corruption)

3. stale_outbox
   outbox_events WHERE published=false AND created_at < now() - STALE_THRESHOLD
   → count and log WARNING (OutboxPublisher handles actual publish)
   → if count > STALE_ALERT_THRESHOLD: emit alert event so monitoring fires

System invariant this upholds:
    An offer_request in a non-terminal state must have exactly one associated
    offer_job in a matching active state (queued/running).
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import structlog
from sqlalchemy import text

from app.offer_processing.domain import (
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    OFFER_STATUS_FAILED,
    OFFER_STATUS_PROCESSING,
    OFFER_STATUS_QUEUED,
    OFFER_TERMINAL_STATUSES,
    RETRY_BACKOFF_SECONDS,
)
from app.worker.offer_queue import OfferJobPayload, enqueue_offer_job

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────
# Thresholds
# ─────────────────────────────────────────────────────────────────

LEASE_GRACE_S            = 2 * 60       # 2 min past leased_until before we act
STUCK_REQUEST_MINUTES    = 10           # offer_request stuck in non-terminal for 10+ min
STALE_OUTBOX_MINUTES     = 5            # unpublished outbox events older than 5 min → alert
STALE_OUTBOX_ALERT_COUNT = 50           # above this many stale events → critical alert

FAST_INTERVAL_S  = 60          # expired leases + stuck requests: check every 1 min
SLOW_INTERVAL_S  = 10 * 60     # outbox drift: check every 10 min

# Legacy alias used by tests that instantiate with reconcile_interval_s= kwarg
_RECONCILE_INTERVAL_S = 5 * 60


class OfferReconciler:
    """Background task that repairs inconsistent offer pipeline state.

    Runs two internal loops:
      fast_loop — expires leases, aligns stuck requests  (every FAST_INTERVAL_S)
      slow_loop — alerts on outbox publisher lag         (every SLOW_INTERVAL_S)

    Both loops wake immediately when stop() is called.
    """

    def __init__(
        self,
        session_factory,
        redis,
        fast_interval_s: float = FAST_INTERVAL_S,
        slow_interval_s: float = SLOW_INTERVAL_S,
        # Legacy compat: tests may pass reconcile_interval_s
        reconcile_interval_s: float | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        if reconcile_interval_s is not None:
            # honour legacy single-interval parameter
            self._fast_interval_s = reconcile_interval_s
            self._slow_interval_s = reconcile_interval_s
        else:
            self._fast_interval_s = fast_interval_s
            self._slow_interval_s = slow_interval_s
        self._running = False
        self._stop_event: asyncio.Event | None = None

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()
        logger.info(
            "offer_reconciler.started",
            fast_interval_s=self._fast_interval_s,
            slow_interval_s=self._slow_interval_s,
            lease_grace_s=LEASE_GRACE_S,
            stuck_request_min=STUCK_REQUEST_MINUTES,
        )
        fast_task = asyncio.create_task(self._fast_loop())
        slow_task = asyncio.create_task(self._slow_loop())
        try:
            await asyncio.gather(fast_task, slow_task)
        except asyncio.CancelledError:
            fast_task.cancel()
            slow_task.cancel()
            await asyncio.gather(fast_task, slow_task, return_exceptions=True)
            raise

    def stop(self) -> None:
        self._running = False
        if self._stop_event is not None:
            self._stop_event.set()
        logger.info("offer_reconciler.stopped")

    async def _sleep(self, seconds: float) -> None:
        """Sleep for `seconds`, but wake immediately when stop() is called."""
        if self._stop_event is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    # ─────────────────────────────────────────────────────────────
    # Fast loop: expired leases + stuck requests  (1 min cadence)
    # ─────────────────────────────────────────────────────────────

    async def _fast_loop(self) -> None:
        while self._running:
            try:
                expired = await self._reconcile_expired_leases()
                stuck   = await self._reconcile_stuck_requests()
                if expired > 0 or stuck > 0:
                    logger.warning(
                        "offer_reconciler.fast_sweep_found_issues",
                        expired_leases_recovered=expired,
                        stuck_requests_reconciled=stuck,
                    )
                else:
                    logger.debug("offer_reconciler.fast_sweep_clean")
            except Exception:
                logger.exception("offer_reconciler.fast_sweep_error")
            await self._sleep(self._fast_interval_s)

    # ─────────────────────────────────────────────────────────────
    # Slow loop: outbox drift alert  (10 min cadence)
    # ─────────────────────────────────────────────────────────────

    async def _slow_loop(self) -> None:
        while self._running:
            try:
                stale = await self._alert_stale_outbox()
                if stale > 0:
                    logger.warning(
                        "offer_reconciler.slow_sweep_found_issues",
                        stale_outbox_events=stale,
                    )
                else:
                    logger.debug("offer_reconciler.slow_sweep_clean")
            except Exception:
                logger.exception("offer_reconciler.slow_sweep_error")
            await self._sleep(self._slow_interval_s)

    # ─────────────────────────────────────────────────────────────
    # sweep_once() — for testing / one-shot invocation
    # ─────────────────────────────────────────────────────────────

    async def sweep_once(self) -> dict[str, int]:
        expired   = await self._reconcile_expired_leases()
        stuck     = await self._reconcile_stuck_requests()
        stale_sse = await self._alert_stale_outbox()
        return {
            "expired_leases_recovered": expired,
            "stuck_requests_reconciled": stuck,
            "stale_outbox_events": stale_sse,
        }

    # ─────────────────────────────────────────────────────────────
    # Check 1: expired leases
    # ─────────────────────────────────────────────────────────────

    async def _reconcile_expired_leases(self) -> int:
        """Find running jobs whose lease expired without an ACK.

        For each expired job:
          - retry_count < max_retries → reset to queued, increment lease_version,
            re-enqueue to Redis
          - retry_count >= max_retries → mark as failed
        """
        grace_cutoff = datetime.now(UTC) - timedelta(seconds=LEASE_GRACE_S)

        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT
                        j.id              AS job_id,
                        j.offer_request_id,
                        j.organization_id,
                        j.idempotency_key,
                        j.attempt,
                        j.retry_count,
                        j.max_retries,
                        j.lease_version,
                        j.last_error_code,
                        j.error_repeat_count,
                        r.work_type_code,
                        r.photo_ids,
                        r.parameters
                    FROM offer_jobs j
                    JOIN offer_requests r ON r.id = j.offer_request_id
                    WHERE j.status = :running
                      AND j.leased_until < :cutoff
                    ORDER BY j.leased_until ASC
                    LIMIT 50
                    FOR UPDATE OF j SKIP LOCKED
                """),
                {"running": JOB_STATUS_RUNNING, "cutoff": grace_cutoff},
            )
            expired_jobs = rows.fetchall()
            if not expired_jobs:
                return 0

            requeue_list = []
            count = 0

            for row in expired_jobs:
                try:
                    will_retry = row.retry_count < row.max_retries
                    new_lease_version = row.lease_version + 1

                    if will_retry:
                        delay_s = RETRY_BACKOFF_SECONDS[
                            min(row.attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                        ]
                        await session.execute(
                            text("""
                                UPDATE offer_jobs
                                SET
                                    status        = 'queued',
                                    worker_id     = NULL,
                                    leased_until  = NULL,
                                    lease_version = :new_lv,
                                    retry_count   = retry_count + 1,
                                    updated_at    = now()
                                WHERE id = :job_id AND status = :running
                            """),
                            {
                                "job_id": row.job_id,
                                "running": JOB_STATUS_RUNNING,
                                "new_lv": new_lease_version,
                            },
                        )
                        await session.execute(
                            text("""
                                UPDATE offer_requests
                                SET status = 'queued', updated_at = now()
                                WHERE id = :req_id
                                  AND status NOT IN ('completed','failed','cancelled')
                            """),
                            {"req_id": row.offer_request_id},
                        )
                        requeue_list.append(row)
                        await session.execute(
                            text("""
                                INSERT INTO reconciler_events
                                    (id, check_type, outcome, offer_job_id,
                                     offer_request_id, organization_id,
                                     old_status, new_status, reason, extra)
                                VALUES
                                    (:id, 'expired_lease', 'requeued', :job_id,
                                     :req_id, :org_id,
                                     'running', 'queued', NULL,
                                     :extra::jsonb)
                            """),
                            {
                                "id": str(uuid4()),
                                "job_id": row.job_id,
                                "req_id": row.offer_request_id,
                                "org_id": row.organization_id,
                                "extra": json.dumps({
                                    "new_lease_version": new_lease_version,
                                    "retry_count": row.retry_count + 1,
                                    "delay_s": delay_s,
                                }),
                            },
                        )
                        logger.warning(
                            "offer_reconciler.expired_lease_requeued",
                            job_id=row.job_id,
                            offer_request_id=row.offer_request_id,
                            new_lease_version=new_lease_version,
                            retry_count=row.retry_count + 1,
                            delay_s=delay_s,
                        )
                    else:
                        await session.execute(
                            text("""
                                UPDATE offer_jobs
                                SET
                                    status        = 'failed',
                                    lease_version = :new_lv,
                                    last_error_code  = 'LEASE_EXPIRED_RETRIES_EXHAUSTED',
                                    last_error_detail = 'Reconciler: lease expired and retries exhausted.',
                                    updated_at    = now()
                                WHERE id = :job_id AND status = :running
                            """),
                            {
                                "job_id": row.job_id,
                                "running": JOB_STATUS_RUNNING,
                                "new_lv": new_lease_version,
                            },
                        )
                        await session.execute(
                            text("""
                                UPDATE offer_requests
                                SET status = 'failed', updated_at = now()
                                WHERE id = :req_id
                                  AND status NOT IN ('completed','failed','cancelled')
                            """),
                            {"req_id": row.offer_request_id},
                        )
                        await session.execute(
                            text("""
                                INSERT INTO outbox_events
                                    (id, event_type, aggregate_type, aggregate_id,
                                     organization_id, payload, published, created_at)
                                VALUES
                                    (:id, 'offer.status_changed', 'offer_request', :req_id,
                                     :org_id,
                                     jsonb_build_object(
                                         'event_id',        :event_id,
                                         'offer_request_id', :req_id,
                                         'job_id',          :job_id,
                                         'status',          'failed',
                                         'source',          'reconciler',
                                         'ts',              to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                                     ),
                                     false, now())
                            """),
                            {
                                "id": str(uuid4()),
                                "event_id": str(uuid4()),
                                "req_id": row.offer_request_id,
                                "org_id": row.organization_id,
                                "job_id": row.job_id,
                            },
                        )
                        await session.execute(
                            text("""
                                INSERT INTO reconciler_events
                                    (id, check_type, outcome, offer_job_id,
                                     offer_request_id, organization_id,
                                     old_status, new_status, reason, extra)
                                VALUES
                                    (:id, 'expired_lease', 'failed_permanently', :job_id,
                                     :req_id, :org_id,
                                     'running', 'failed',
                                     'LEASE_EXPIRED_RETRIES_EXHAUSTED',
                                     :extra::jsonb)
                            """),
                            {
                                "id": str(uuid4()),
                                "job_id": row.job_id,
                                "req_id": row.offer_request_id,
                                "org_id": row.organization_id,
                                "extra": json.dumps({
                                    "retry_count": row.retry_count,
                                    "max_retries": row.max_retries,
                                }),
                            },
                        )
                        logger.error(
                            "offer_reconciler.expired_lease_failed_permanently",
                            job_id=row.job_id,
                            offer_request_id=row.offer_request_id,
                            retry_count=row.retry_count,
                            max_retries=row.max_retries,
                        )
                    count += 1
                except Exception:
                    logger.exception(
                        "offer_reconciler.expired_lease_row_error",
                        job_id=row.job_id,
                    )

            await session.commit()

        # Re-enqueue re-queued jobs to Redis outside the DB session
        for row in requeue_list:
            try:
                await enqueue_offer_job(
                    self._redis,
                    payload=OfferJobPayload(
                        job_id=row.job_id,
                        offer_request_id=row.offer_request_id,
                        organization_id=row.organization_id,
                        work_type_code=row.work_type_code,
                        idempotency_key=row.idempotency_key,
                        photo_ids=list(row.photo_ids or []),
                        parameters=dict(row.parameters or {}),
                        attempt=row.attempt,
                    ),
                )
            except Exception:
                logger.exception(
                    "offer_reconciler.reenqueue_failed",
                    job_id=row.job_id,
                )

        return count

    # ─────────────────────────────────────────────────────────────
    # Check 2: stuck offer_requests with no active job
    # ─────────────────────────────────────────────────────────────

    async def _reconcile_stuck_requests(self) -> int:
        """Find offer_requests stuck in queued/processing with no active job.

        This catches data divergence between offer_requests and offer_jobs
        caused by partial failures during status transitions.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=STUCK_REQUEST_MINUTES)

        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT r.id, r.organization_id, r.status
                    FROM offer_requests r
                    WHERE r.status IN ('queued', 'processing')
                      AND r.updated_at < :cutoff
                      AND NOT EXISTS (
                          SELECT 1 FROM offer_jobs j
                          WHERE j.offer_request_id = r.id
                            AND j.status IN ('queued', 'running')
                      )
                    ORDER BY r.updated_at ASC
                    LIMIT 50
                    FOR UPDATE OF r SKIP LOCKED
                """),
                {"cutoff": cutoff},
            )
            stuck = rows.fetchall()
            if not stuck:
                return 0

            count = 0
            for row in stuck:
                try:
                    latest = await session.execute(
                        text("""
                            SELECT status, last_error_code
                            FROM offer_jobs
                            WHERE offer_request_id = :req_id
                            ORDER BY created_at DESC
                            LIMIT 1
                        """),
                        {"req_id": row.id},
                    )
                    latest_job = latest.fetchone()

                    if latest_job is None:
                        reconciled_status = OFFER_STATUS_FAILED
                        reason = "no_jobs_found"
                    elif latest_job.status in ("completed", "failed", "cancelled"):
                        reconciled_status = {
                            "completed": "needs_review",
                            "failed": OFFER_STATUS_FAILED,
                            "cancelled": "cancelled",
                        }.get(latest_job.status, OFFER_STATUS_FAILED)
                        reason = f"aligned_with_job_{latest_job.status}"
                    else:
                        reconciled_status = OFFER_STATUS_FAILED
                        reason = f"job_in_unexpected_state_{latest_job.status}"

                    await session.execute(
                        text("""
                            UPDATE offer_requests
                            SET status = :new_status, updated_at = now()
                            WHERE id = :req_id
                              AND status IN ('queued', 'processing')
                        """),
                        {"req_id": row.id, "new_status": reconciled_status},
                    )
                    await session.execute(
                        text("""
                            INSERT INTO outbox_events
                                (id, event_type, aggregate_type, aggregate_id,
                                 organization_id, payload, published, created_at)
                            VALUES
                                (:id, 'offer.status_changed', 'offer_request', :req_id,
                                 :org_id,
                                 jsonb_build_object(
                                     'event_id',         :event_id,
                                     'offer_request_id', :req_id,
                                     'status',           :new_status,
                                     'source',           'reconciler',
                                     'reason',           :reason,
                                     'ts',               to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                                 ),
                                 false, now())
                        """),
                        {
                            "id": str(uuid4()),
                            "event_id": str(uuid4()),
                            "req_id": row.id,
                            "org_id": row.organization_id,
                            "new_status": reconciled_status,
                            "reason": reason,
                        },
                    )
                    await session.execute(
                        text("""
                            INSERT INTO reconciler_events
                                (id, check_type, outcome, offer_job_id,
                                 offer_request_id, organization_id,
                                 old_status, new_status, reason, extra)
                            VALUES
                                (:id, 'stuck_request', 'reconciled', NULL,
                                 :req_id, :org_id,
                                 :old_status, :new_status, :reason, NULL)
                        """),
                        {
                            "id": str(uuid4()),
                            "req_id": row.id,
                            "org_id": row.organization_id,
                            "old_status": row.status,
                            "new_status": reconciled_status,
                            "reason": reason[:128],
                        },
                    )
                    logger.error(
                        "offer_reconciler.stuck_request_reconciled",
                        offer_request_id=row.id,
                        old_status=row.status,
                        new_status=reconciled_status,
                        reason=reason,
                    )
                    count += 1
                except Exception:
                    logger.exception(
                        "offer_reconciler.stuck_request_row_error",
                        offer_request_id=row.id,
                    )

            await session.commit()
        return count

    # ─────────────────────────────────────────────────────────────
    # Check 3: stale outbox events (publisher lag alert)
    # ─────────────────────────────────────────────────────────────

    async def _alert_stale_outbox(self) -> int:
        """Count unpublished outbox events older than STALE_OUTBOX_MINUTES.

        The OutboxPublisher handles the actual publishing.  This check is
        purely observational — it alerts if the publisher appears to be stuck.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=STALE_OUTBOX_MINUTES)

        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM outbox_events
                    WHERE published = false
                      AND created_at < :cutoff
                """),
                {"cutoff": cutoff},
            )
            cnt = result.scalar_one() or 0

        if cnt >= STALE_OUTBOX_ALERT_COUNT:
            logger.error(
                "offer_reconciler.outbox_publisher_critical",
                stale_count=cnt,
                older_than_minutes=STALE_OUTBOX_MINUTES,
                hint="OutboxPublisher may be stuck — check worker process",
            )
            async with self._session_factory() as session:
                await session.execute(
                    text("""
                        INSERT INTO reconciler_events
                            (id, check_type, outcome,
                             offer_job_id, offer_request_id, organization_id,
                             old_status, new_status, reason, extra)
                        VALUES
                            (:id, 'stale_outbox', 'alert',
                             NULL, NULL, NULL,
                             NULL, NULL, 'stale_outbox_alert',
                             :extra::jsonb)
                    """),
                    {
                        "id": str(uuid4()),
                        "extra": json.dumps({
                            "stale_count": cnt,
                            "threshold": STALE_OUTBOX_ALERT_COUNT,
                            "older_than_minutes": STALE_OUTBOX_MINUTES,
                        }),
                    },
                )
                await session.commit()
        elif cnt > 0:
            logger.warning(
                "offer_reconciler.outbox_publisher_lag",
                stale_count=cnt,
                older_than_minutes=STALE_OUTBOX_MINUTES,
            )
        return cnt
