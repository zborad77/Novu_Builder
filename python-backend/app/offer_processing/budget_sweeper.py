"""Budget reservation expiry sweeper.

Recovers tokens from reservations that were never released due to hard process
death (kill -9, OOM kill, power outage, VM eviction).

Every job that calls budget.reserve() creates a row in ai_budget_reservations
with status='reserved'.  Controlled failures call release() or record_actual()
which transitions the row to 'released' or 'consumed'.

Rows that remain 'reserved' past RESERVATION_EXPIRY_MINUTES indicate the
worker that owned them died without cleanup.  The sweeper transitions them to
'expired' and credits the tokens back to daily_tokens_used.

Designed to run as a background task within the offer worker process.
Run interval: every 5 minutes (configurable).
"""
from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text

from app.offer_processing.budget import RESERVATION_EXPIRY_MINUTES

logger = structlog.get_logger(__name__)

_DEFAULT_SWEEP_INTERVAL_S = 5 * 60   # 5 minutes


class BudgetSweeper:
    """Background task that recovers tokens from stale reservations."""

    def __init__(
        self,
        session_factory,
        sweep_interval_s: float = _DEFAULT_SWEEP_INTERVAL_S,
        expiry_minutes: int = RESERVATION_EXPIRY_MINUTES,
    ) -> None:
        self._session_factory = session_factory
        self._sweep_interval_s = sweep_interval_s
        self._expiry_minutes = expiry_minutes
        self._running = False
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()
        logger.info(
            "budget_sweeper.started",
            sweep_interval_s=self._sweep_interval_s,
            expiry_minutes=self._expiry_minutes,
        )
        while self._running:
            try:
                swept = await self.sweep_once()
                if swept > 0:
                    logger.info("budget_sweeper.recovered", count=swept)
            except Exception:
                logger.exception("budget_sweeper.error")
            await self._sleep(self._sweep_interval_s)

    def stop(self) -> None:
        self._running = False
        if self._stop_event is not None:
            self._stop_event.set()
        logger.info("budget_sweeper.stopped")

    async def _sleep(self, seconds: float) -> None:
        """Sleep for `seconds`, but wake immediately when stop() is called."""
        if self._stop_event is None:
            await asyncio.sleep(seconds)
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def sweep_once(self) -> int:
        """Find and expire stale reservations. Returns the count swept."""
        async with self._session_factory() as session:
            # Lock stale rows for update, skip any locked by a concurrent sweep
            rows = await session.execute(
                text("""
                    SELECT id, organization_id, offer_job_id, token_estimate
                    FROM ai_budget_reservations
                    WHERE status = 'reserved'
                      AND reserved_at < now() - :expiry_interval::interval
                    ORDER BY reserved_at ASC
                    LIMIT 200
                    FOR UPDATE SKIP LOCKED
                """),
                {"expiry_interval": f"{self._expiry_minutes} minutes"},
            )
            stale = rows.fetchall()
            if not stale:
                return 0

            swept_ids = []
            for row in stale:
                try:
                    # Mark expired
                    await session.execute(
                        text("""
                            UPDATE ai_budget_reservations
                            SET status = 'expired', expired_at = now()
                            WHERE id = :id AND status = 'reserved'
                        """),
                        {"id": row.id},
                    )
                    # Credit tokens back
                    await session.execute(
                        text("""
                            UPDATE organization_ai_budgets
                            SET
                                daily_tokens_used = GREATEST(0, daily_tokens_used - :estimate),
                                updated_at = now()
                            WHERE organization_id = :org_id
                        """),
                        {"org_id": row.organization_id, "estimate": row.token_estimate},
                    )
                    swept_ids.append(row.id)
                    logger.warning(
                        "budget_sweeper.reservation_expired",
                        reservation_id=row.id,
                        offer_job_id=row.offer_job_id,
                        organization_id=row.organization_id,
                        token_estimate=row.token_estimate,
                    )
                except Exception:
                    logger.exception(
                        "budget_sweeper.row_error",
                        reservation_id=row.id,
                    )

            await session.commit()
            return len(swept_ids)
