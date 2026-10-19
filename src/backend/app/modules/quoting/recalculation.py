"""Implementace portu analysis.QuoteRecalculator (rekalkulace na analytické frontě)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.work_catalog_repository import WorkCatalogRepository
from app.modules.quoting.quote_variant_repository import QuoteVariantRepository
from app.modules.quoting.quote_variant_service import QuoteVariantRecalculationResult, QuoteVariantService


class QuoteVariantRecalculator:
    async def recalculate(self, session: AsyncSession, project_id: str) -> QuoteVariantRecalculationResult | None:
        return await QuoteVariantService(
            QuoteVariantRepository(session),
            WorkCatalogRepository(session),
        ).recalculate_quote_variants_with_context(
            project_id,
            raise_on_unavailable=True,
        )

    def output_summary(self, result: QuoteVariantRecalculationResult) -> dict[str, object]:
        return QuoteVariantService.build_recalculation_output_summary(result)
