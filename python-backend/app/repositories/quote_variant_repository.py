import json
import structlog
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.case_workflow.transitions import TransitionError, apply_transition
from app.core.events import AGGREGATE_CASE, EVENT_PROPOSAL_READY
from app.models import AnalysisJob, AnalysisResult, MaterialCatalog, PricingProfile, Project, QuoteItem, QuoteVariant, SupplierMaterialPrice
from app.offer_processing.outbox import build_outbox_event

logger = structlog.get_logger(__name__)


class QuoteVariantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_analysis_job_in_org(
        self,
        job_id: str,
        organization_id: str,
    ) -> AnalysisJob | None:
        result = await self.session.execute(
            select(AnalysisJob)
            .join(Project, Project.id == AnalysisJob.project_id)
            .where(
                AnalysisJob.id == job_id,
                Project.organization_id == organization_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_project(self, project_id: str) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_latest_analysis(self, project_id: str) -> AnalysisResult | None:
        result = await self.session.execute(
            select(AnalysisResult)
            .where(AnalysisResult.project_id == project_id)
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_default_pricing_profile(self, organization_id: str) -> PricingProfile | None:
        result = await self.session.execute(
            select(PricingProfile)
            .where(PricingProfile.organization_id == organization_id, PricingProfile.is_default.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_quote_variants(self, project_id: str) -> list[QuoteVariant]:
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.project_id == project_id)
            .order_by(QuoteVariant.created_at.asc(), QuoteVariant.id.asc())
        )
        return list(result.scalars().all())

    async def get_quote_variant(self, variant_id: str) -> QuoteVariant | None:
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def list_materials_by_names(self, organization_id: str, names: list[str]) -> list[MaterialCatalog]:
        if not names:
            return []
        lowered_names = [name.lower() for name in names]
        result = await self.session.execute(
            select(MaterialCatalog)
            .where(
                MaterialCatalog.organization_id == organization_id,
                MaterialCatalog.is_active.is_(True),
                func.lower(MaterialCatalog.name).in_(lowered_names),
            )
            .order_by(MaterialCatalog.name.asc())
        )
        return list(result.scalars().all())

    async def get_lowest_supplier_price(self, material_catalog_id: str) -> SupplierMaterialPrice | None:
        result = await self.session.execute(
            select(SupplierMaterialPrice)
            .where(SupplierMaterialPrice.material_catalog_id == material_catalog_id)
            .order_by(SupplierMaterialPrice.unit_price.asc(), SupplierMaterialPrice.supplier_id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def replace_project_variants(
        self,
        *,
        project: Project,
        analysis: AnalysisResult | None,
        pricing_profile: PricingProfile,
        variants_payload: list[dict],
    ) -> tuple[list[QuoteVariant], str | None]:
        existing_variants = await self.list_quote_variants(project.id)
        existing_variant_ids = [variant.id for variant in existing_variants]
        if existing_variant_ids:
            await self.session.execute(delete(QuoteItem).where(QuoteItem.quote_variant_id.in_(existing_variant_ids)))
            await self.session.execute(delete(QuoteVariant).where(QuoteVariant.id.in_(existing_variant_ids)))
            await self.session.flush()

        timestamp = datetime.now(UTC)
        created_variant_ids: list[str] = []

        for variant_payload in variants_payload:
            variant = QuoteVariant(
                id=variant_payload["id"],
                project_id=project.id,
                analysis_result_id=analysis.id if analysis else None,
                pricing_profile_id=pricing_profile.id,
                variant_type=variant_payload["variant_type"],
                labor_cost=variant_payload["labor_cost"],
                material_cost=variant_payload["material_cost"],
                other_cost=variant_payload["other_cost"],
                margin_pct=variant_payload["margin_pct"],
                total_ex_vat=variant_payload["total_ex_vat"],
                vat_amount=variant_payload["vat_amount"],
                total_inc_vat=variant_payload["total_inc_vat"],
                currency=variant_payload.get("currency", pricing_profile.currency),
                vat_pct=variant_payload.get("vat_pct", pricing_profile.vat_pct),
                pricing_summary_json=variant_payload.get("pricing_summary_json"),
                created_at=timestamp,
                updated_at=timestamp,
            )
            self.session.add(variant)
            created_variant_ids.append(variant.id)

            for item_payload in variant_payload["items"]:
                self.session.add(
                    QuoteItem(
                        id=item_payload["id"],
                        quote_variant_id=variant.id,
                        project_work_item_id=item_payload.get("project_work_item_id"),
                        catalog_pricing_profile_id=item_payload.get("catalog_pricing_profile_id"),
                        work_type_code=item_payload.get("work_type_code"),
                        resolved_catalog_pricing_profile_code=item_payload.get("resolved_catalog_pricing_profile_code"),
                        resolved_catalog_pricing_profile_version=item_payload.get("resolved_catalog_pricing_profile_version"),
                        catalog_pricing_rule_code=item_payload.get("catalog_pricing_rule_code"),
                        item_type=item_payload["item_type"],
                        name=item_payload["name"],
                        description=item_payload.get("description"),
                        quantity=item_payload["quantity"],
                        unit=item_payload["unit"],
                        unit_price=item_payload["unit_price"],
                        total_price=item_payload["total_price"],
                        material_catalog_id=item_payload.get("material_catalog_id"),
                        supplier_id=item_payload.get("supplier_id"),
                        price_source=item_payload["price_source"],
                        is_manual_override=item_payload["is_manual_override"],
                        ai_suggested_unit_price=item_payload.get("ai_suggested_unit_price"),
                        supplier_reference_unit_price=item_payload.get("supplier_reference_unit_price"),
                        company_default_unit_price=item_payload.get("company_default_unit_price"),
                        sort_order=item_payload["sort_order"],
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )

        # Transition project analyzing → proposal_ready and write the outbox event
        # in the same transaction as the DELETE + INSERT above.
        # Invariant: no window where variants are visible but status hasn't advanced
        # and no window where status advanced but the SSE replay row is missing.
        proposal_event_id: str | None = None
        try:
            apply_transition(
                project,
                "proposal_ready",
                actor_user_id=None,
                reason="Quote variants generated",
                session=self.session,
            )
            outbox_event = build_outbox_event(
                event_type=EVENT_PROPOSAL_READY,
                aggregate_type=AGGREGATE_CASE,
                aggregate_id=project.id,
                organization_id=project.organization_id,
                payload={"status": "proposal_ready"},
            )
            self.session.add(outbox_event)
            proposal_event_id = outbox_event.id
        except TransitionError:
            logger.warning(
                "quote_variant.status_transition_skipped",
                project_id=project.id,
                current_status=project.status,
                reason="Cannot transition to proposal_ready from current status — status unchanged",
            )
        project.updated_at = timestamp
        await self.session.commit()

        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id.in_(created_variant_ids))
            .order_by(QuoteVariant.created_at.asc(), QuoteVariant.id.asc())
        )
        return list(result.scalars().all()), proposal_event_id

    async def update_quote_variant(self, variant: QuoteVariant, changes: dict) -> QuoteVariant:
        for key, value in changes.items():
            setattr(variant, key, value)
        variant.updated_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(variant)
        result = await self.session.execute(
            select(QuoteVariant)
            .options(selectinload(QuoteVariant.items))
            .where(QuoteVariant.id == variant.id)
        )
        return result.scalar_one()

    @staticmethod
    def parse_json_field(value: str | None):
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def build_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:10]}"
