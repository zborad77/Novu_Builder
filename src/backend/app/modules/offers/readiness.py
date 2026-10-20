"""Připravenost offer workeru: AI provider a backlog před zapnutím.

- `AI_OFFER_PROVIDER=mock` (výchozí) je bezpečný – žádná volání externí AI.
- `AI_OFFER_PROVIDER=claude` vyžaduje explicitní konfiguraci: skutečný
  `ANTHROPIC_API_KEY` (ne prázdný ani placeholder) a tvrdé rozpočtové limity
  u všech organizací. Jinak offer worker odmítne start.
- `collect_offer_backlog` vyčíslí, co by worker po zapnutí zpracoval nebo
  odeslal (offer joby, rozpracované requesty, nepublikovaný outbox, Redis
  fronta) – `scripts/offer_backlog_report.py` a `nc-provision offer-worker`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.config import is_insecure_placeholder
from app.platform.jobs.offer_queue import (
    OFFER_PROCESSING_KEY,
    OFFER_QUEUE_HIGH,
    OFFER_QUEUE_LOW,
    OFFER_QUEUE_NORMAL,
)

SUPPORTED_OFFER_PROVIDERS = ("mock", "claude")


class OfferWorkerNotReadyError(RuntimeError):
    """Konfigurace nedovoluje offer worker spustit."""


@dataclass(frozen=True)
class OfferBacklog:
    offer_jobs_queued: int
    offer_jobs_running: int
    offer_requests_in_progress: int
    outbox_unpublished: int
    outbox_oldest_unpublished_at: datetime | None
    redis_offer_queue: int | None
    redis_offer_processing: int | None

    @property
    def would_call_ai(self) -> bool:
        """Zda by zapnutý worker hned zpracovával offer joby (volání AI)."""
        queued_in_redis = self.redis_offer_queue or 0
        return bool(self.offer_jobs_queued or self.offer_jobs_running or queued_in_redis)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["would_call_ai"] = self.would_call_ai
        return data


async def check_offer_provider_ready(settings: Any, session: AsyncSession) -> str:
    """Vrátí normalizovaný provider nebo vyhodí OfferWorkerNotReadyError."""
    provider = (getattr(settings, "ai_offer_provider", "") or "").strip().lower()
    if provider not in SUPPORTED_OFFER_PROVIDERS:
        raise OfferWorkerNotReadyError(
            f"AI_OFFER_PROVIDER={provider!r} is not supported (allowed: {', '.join(SUPPORTED_OFFER_PROVIDERS)})."
        )
    if provider == "mock":
        return provider

    api_key = (getattr(settings, "anthropic_api_key", None) or "").strip()
    if not api_key or is_insecure_placeholder(api_key):
        raise OfferWorkerNotReadyError(
            "AI_OFFER_PROVIDER=claude requires a real ANTHROPIC_API_KEY (empty or placeholder value found)."
        )
    soft_budgets = (
        await session.execute(
            text(
                """
                SELECT count(*) FROM organization_ai_budgets
                WHERE is_hard_limit = false
                   OR daily_token_limit <= 0
                   OR monthly_cost_limit_usd <= 0
                """
            )
        )
    ).scalar_one()
    if soft_budgets:
        raise OfferWorkerNotReadyError(
            f"AI_OFFER_PROVIDER=claude requires hard AI budget limits: {soft_budgets} organization budget(s) "
            "are soft (is_hard_limit=false) or have a non-positive limit."
        )
    return provider


async def collect_offer_backlog(session: AsyncSession, redis: Any | None = None) -> OfferBacklog:
    job_rows = (
        await session.execute(
            text("SELECT status, count(*) FROM offer_jobs WHERE status IN ('queued', 'running') GROUP BY status")
        )
    ).all()
    jobs: dict[str, int] = {str(row[0]): int(row[1]) for row in job_rows}
    requests_in_progress = (
        await session.execute(
            text("SELECT count(*) FROM offer_requests WHERE status IN ('submitted', 'queued', 'processing')")
        )
    ).scalar_one()
    outbox_count, outbox_oldest = (
        await session.execute(
            text("SELECT count(*), min(created_at) FROM outbox_events WHERE published = false")
        )
    ).one()

    redis_queue: int | None = None
    redis_processing: int | None = None
    if redis is not None:
        redis_queue = 0
        for key in (OFFER_QUEUE_HIGH, OFFER_QUEUE_NORMAL, OFFER_QUEUE_LOW):
            redis_queue += int(await redis.llen(key) or 0)
        redis_processing = int(await redis.llen(OFFER_PROCESSING_KEY) or 0)

    return OfferBacklog(
        offer_jobs_queued=int(jobs.get("queued", 0)),
        offer_jobs_running=int(jobs.get("running", 0)),
        offer_requests_in_progress=int(requests_in_progress),
        outbox_unpublished=int(outbox_count),
        outbox_oldest_unpublished_at=outbox_oldest,
        redis_offer_queue=redis_queue,
        redis_offer_processing=redis_processing,
    )
