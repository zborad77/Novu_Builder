"""Porty modulu workflow – volání do modulů nad workflow (exports).

Implementaci registruje app.composition.wiring.init_modules(); neregistrovaný port
vyhodí RuntimeError.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class FinalProposalExporter(Protocol):
    """Exporty finálního návrhu (implementuje modul exports – ExportService)."""

    async def create_final_proposal_exports(
        self, *, case_detail: Any, timeline_events: list[dict] | None = None
    ) -> Any: ...


FinalProposalExporterFactory = Callable[[AsyncSession], FinalProposalExporter]

_exporter_factory: FinalProposalExporterFactory | None = None


def register_final_proposal_exporter_factory(factory: FinalProposalExporterFactory) -> None:
    global _exporter_factory
    _exporter_factory = factory


def final_proposal_exporter(session: AsyncSession) -> FinalProposalExporter:
    if _exporter_factory is None:
        raise RuntimeError(
            "workflow: final proposal exporter is not registered (call app.composition.wiring.init_modules())"
        )
    return _exporter_factory(session)
