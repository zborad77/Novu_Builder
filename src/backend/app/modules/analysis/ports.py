"""Porty modulu analysis – volání do modulů nad analysis (quoting, workflow).

Rekalkulace nabídky běží jako typ jobu na analytické frontě; samotný výpočet patří
modulu quoting a posun zakázky do proposal_ready modulu workflow. Implementace
registruje app.composition.wiring.init_modules(); neregistrovaný port vyhodí
RuntimeError (job selže viditelně, nikdy se tiše nepřeskočí).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class QuoteRecalculationUnavailableError(ValueError):
    """Varianty nabídky nelze z aktuálního stavu zakázky přepočítat (bázová třída)."""


class QuoteRecalculator(Protocol):
    """Implementuje modul quoting (QuoteVariantService)."""

    async def recalculate(self, session: AsyncSession, project_id: str) -> Any:
        """Přepočítá varianty nabídky; při nedostupnosti vyhodí QuoteRecalculationUnavailableError."""

    def output_summary(self, result: Any) -> dict[str, object]:
        """Textový souhrn výsledku pro output_summary analytického jobu."""

# (session, project_id, reason) -> None; vyhazuje cases.errors.CaseActionError při neplatném přechodu
ProposalReadyNotifier = Callable[[AsyncSession, str, str], Awaitable[None]]

_quote_recalculator: QuoteRecalculator | None = None
_proposal_ready_notifier: ProposalReadyNotifier | None = None


def register_quote_recalculator(recalculator: QuoteRecalculator) -> None:
    global _quote_recalculator
    _quote_recalculator = recalculator


def register_proposal_ready_notifier(notifier: ProposalReadyNotifier) -> None:
    global _proposal_ready_notifier
    _proposal_ready_notifier = notifier


def _recalculator() -> QuoteRecalculator:
    if _quote_recalculator is None:
        raise RuntimeError(
            "analysis: quote recalculator is not registered (call app.composition.wiring.init_modules())"
        )
    return _quote_recalculator


async def recalculate_quotes(session: AsyncSession, project_id: str) -> Any:
    return await _recalculator().recalculate(session, project_id)


def quote_recalculation_output_summary(result: Any) -> dict[str, object]:
    return _recalculator().output_summary(result)


async def notify_proposal_ready(session: AsyncSession, project_id: str, reason: str) -> None:
    if _proposal_ready_notifier is None:
        raise RuntimeError(
            "analysis: proposal-ready notifier is not registered (call app.composition.wiring.init_modules())"
        )
    await _proposal_ready_notifier(session, project_id, reason)
