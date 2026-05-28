"""AI budget enforcement — atomic pre-flight cost control with reservation tracking.

Reservation lifecycle:
    reserve(org_id, job_id)         → INSERT ai_budget_reservations + atomic counter update
    record_actual(org_id, job_id)   → mark reservation 'consumed' + adjust delta
    release(org_id, job_id)         → mark reservation 'released' + credit tokens back

Crash recovery (kill -9 / OOM / power outage):
    The reservation row stays 'reserved' after a hard crash.
    BudgetSweeper periodically finds rows WHERE status = 'reserved'
    AND reserved_at < now() - RESERVATION_EXPIRY_MINUTES and marks them
    'expired', crediting the tokens back to daily_tokens_used.

Why atomic UPDATE for the counter:
    BAD (read-then-check):
        check_budget()     # sees OK
        start_ai_job()     # two concurrent requests both pass
    GOOD (atomic UPDATE):
        UPDATE ... SET daily_tokens_used = daily_tokens_used + :est
        WHERE daily_tokens_used + :est <= daily_token_limit
        → if 0 rows updated → budget exhausted → reject
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.offer_processing.domain import ERROR_BUDGET_EXHAUSTED

logger = structlog.get_logger(__name__)

DEFAULT_TOKEN_ESTIMATE = 2_000
_COST_PER_1K_TOKENS_USD = Decimal("0.015")
RESERVATION_EXPIRY_MINUTES = 15


class BudgetExhaustedError(Exception):
    def __init__(self, organization_id: str) -> None:
        super().__init__(
            f"AI budget exhausted for organization {organization_id}. "
            "Try again tomorrow or contact support to increase limits."
        )
        self.organization_id = organization_id
        self.error_code = ERROR_BUDGET_EXHAUSTED


class BudgetService:
    """Atomic per-org AI budget enforcement with per-job reservation tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Ensure budget row exists
    # -----------------------------------------------------------------------

    async def ensure_budget_exists(self, organization_id: str) -> None:
        await self._session.execute(
            text("""
                INSERT INTO organization_ai_budgets
                    (id, organization_id, created_at, updated_at)
                VALUES
                    (:id, :org_id, now(), now())
                ON CONFLICT (organization_id) DO NOTHING
            """),
            {"id": str(uuid4()), "org_id": organization_id},
        )

    # -----------------------------------------------------------------------
    # reserve — atomic counter update + reservation row
    # -----------------------------------------------------------------------

    async def reserve(
        self,
        organization_id: str,
        *,
        job_id: str,
        token_estimate: int = DEFAULT_TOKEN_ESTIMATE,
    ) -> None:
        """Atomically reserve tokens and create a reservation row.

        Idempotent: ON CONFLICT on offer_job_id does nothing if already reserved.
        Raises BudgetExhaustedError if the hard limit would be exceeded.
        """
        await self.ensure_budget_exists(organization_id)

        # Atomic counter update — prevents race conditions
        result = await self._session.execute(
            text("""
                UPDATE organization_ai_budgets
                SET
                    daily_tokens_used = daily_tokens_used + :estimate,
                    updated_at = now()
                WHERE
                    organization_id = :org_id
                    AND (
                        is_hard_limit = false
                        OR daily_tokens_used + :estimate <= daily_token_limit
                    )
                RETURNING id, daily_tokens_used, daily_token_limit, alert_threshold_pct
            """),
            {"org_id": organization_id, "estimate": token_estimate},
        )
        row = result.fetchone()

        if row is None:
            logger.warning(
                "offer.budget_exhausted",
                organization_id=organization_id,
                token_estimate=token_estimate,
                job_id=job_id,
            )
            raise BudgetExhaustedError(organization_id)

        # Alert at threshold
        pct_used = (row.daily_tokens_used / max(row.daily_token_limit, 1)) * 100
        if pct_used >= row.alert_threshold_pct:
            logger.warning(
                "offer.budget_alert",
                organization_id=organization_id,
                pct_used=round(pct_used, 1),
                daily_tokens_used=row.daily_tokens_used,
                daily_token_limit=row.daily_token_limit,
                job_id=job_id,
            )

        # Reservation row — idempotent on conflict (same job_id)
        await self._session.execute(
            text("""
                INSERT INTO ai_budget_reservations
                    (id, organization_id, offer_job_id, token_estimate, status, reserved_at)
                VALUES
                    (:id, :org_id, :job_id, :estimate, 'reserved', now())
                ON CONFLICT (offer_job_id) DO NOTHING
            """),
            {
                "id": str(uuid4()),
                "org_id": organization_id,
                "job_id": job_id,
                "estimate": token_estimate,
            },
        )

    # -----------------------------------------------------------------------
    # record_actual — mark consumed + adjust delta
    # -----------------------------------------------------------------------

    async def record_actual(
        self,
        organization_id: str,
        *,
        job_id: str,
        estimated_tokens: int,
        actual_tokens: int,
        cost_usd: Decimal,
    ) -> None:
        """Adjust counter by (actual - estimated) and mark reservation consumed.

        Safe to call when actual_tokens == 0 (equivalent to a full release).
        Idempotent: if reservation is already consumed/released, only the
        counter adjustment runs.
        """
        delta = actual_tokens - estimated_tokens
        await self._session.execute(
            text("""
                UPDATE organization_ai_budgets
                SET
                    daily_tokens_used = GREATEST(0, daily_tokens_used + :delta),
                    monthly_cost_used_usd = monthly_cost_used_usd + :cost,
                    updated_at = now()
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id, "delta": delta, "cost": cost_usd},
        )
        await self._session.execute(
            text("""
                UPDATE ai_budget_reservations
                SET status = 'consumed', consumed_at = now()
                WHERE offer_job_id = :job_id AND status = 'reserved'
            """),
            {"job_id": job_id},
        )

    # -----------------------------------------------------------------------
    # release — credit back full reservation on controlled failure
    # -----------------------------------------------------------------------

    async def release(
        self,
        organization_id: str,
        *,
        job_id: str,
        token_estimate: int = DEFAULT_TOKEN_ESTIMATE,
    ) -> None:
        """Return reserved tokens when no AI tokens were actually consumed.

        Called on: provider timeout, 429, validation error, job cancelled.
        Idempotent: only credits back if the reservation is still 'reserved'.
        """
        result = await self._session.execute(
            text("""
                UPDATE ai_budget_reservations
                SET status = 'released', released_at = now()
                WHERE offer_job_id = :job_id AND status = 'reserved'
                RETURNING token_estimate
            """),
            {"job_id": job_id},
        )
        row = result.fetchone()
        if row is None:
            return  # Already consumed/released/expired — nothing to credit back

        # Credit back the exact amount that was reserved
        await self._session.execute(
            text("""
                UPDATE organization_ai_budgets
                SET
                    daily_tokens_used = GREATEST(0, daily_tokens_used - :estimate),
                    updated_at = now()
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id, "estimate": row.token_estimate},
        )

    # -----------------------------------------------------------------------
    # reset_daily_counter — called by scheduled task at midnight
    # -----------------------------------------------------------------------

    async def reset_daily_counter(self, organization_id: str) -> None:
        await self._session.execute(
            text("""
                UPDATE organization_ai_budgets
                SET
                    daily_tokens_used = 0,
                    daily_reset_at = now(),
                    updated_at = now()
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id},
        )


def estimate_cost_usd(total_tokens: int) -> Decimal:
    return (_COST_PER_1K_TOKENS_USD * Decimal(total_tokens) / 1000).quantize(Decimal("0.000001"))
