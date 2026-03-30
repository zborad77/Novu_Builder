from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import PricingProfile, Project
from app.models.work_catalog import (
    AnalysisProfile,
    CatalogPricingProfile,
    ProjectWorkItem,
    ProjectWorkItemValue,
    TenantWorkTypeParameterOverride,
    TenantWorkTypeSetting,
    VisionDetection,
    WorkType,
    WorkTypeParameter,
)


class WorkCatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _work_type_detail_query(self) -> Select[tuple[WorkType]]:
        return (
            select(WorkType)
            .options(
                selectinload(WorkType.category),
                selectinload(WorkType.parameters).selectinload(WorkTypeParameter.options),
                selectinload(WorkType.default_analysis_profile),
                selectinload(WorkType.default_catalog_pricing_profile),
            )
        )

    async def get_project_in_org(self, project_id: str, organization_id: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_work_types(self) -> Sequence[WorkType]:
        result = await self.session.execute(
            self._work_type_detail_query().order_by(WorkType.sort_order.asc(), WorkType.code.asc())
        )
        return result.scalars().all()

    async def get_work_type_by_code(self, work_type_code: str) -> WorkType | None:
        result = await self.session.execute(
            self._work_type_detail_query().where(WorkType.code == work_type_code)
        )
        return result.scalar_one_or_none()

    async def list_tenant_settings_for_org(
        self,
        organization_id: str,
        *,
        work_type_ids: Sequence[str] | None = None,
    ) -> dict[str, TenantWorkTypeSetting]:
        query = (
            select(TenantWorkTypeSetting)
            .options(
                selectinload(TenantWorkTypeSetting.analysis_profile),
                selectinload(TenantWorkTypeSetting.catalog_pricing_profile),
            )
            .where(TenantWorkTypeSetting.organization_id == organization_id)
        )
        if work_type_ids:
            query = query.where(TenantWorkTypeSetting.work_type_id.in_(tuple(work_type_ids)))
        result = await self.session.execute(query)
        rows = result.scalars().all()
        return {row.work_type_id: row for row in rows}

    async def list_parameter_overrides_for_org(
        self,
        organization_id: str,
        *,
        work_type_ids: Sequence[str] | None = None,
    ) -> dict[str, TenantWorkTypeParameterOverride]:
        query = (
            select(TenantWorkTypeParameterOverride)
            .options(selectinload(TenantWorkTypeParameterOverride.parameter))
            .where(TenantWorkTypeParameterOverride.organization_id == organization_id)
        )
        if work_type_ids:
            query = query.where(TenantWorkTypeParameterOverride.work_type_id.in_(tuple(work_type_ids)))
        result = await self.session.execute(query)
        rows = result.scalars().all()
        return {row.work_type_parameter_id: row for row in rows}

    async def get_analysis_profile_by_code(self, code: str) -> AnalysisProfile | None:
        result = await self.session.execute(
            select(AnalysisProfile).where(AnalysisProfile.code == code)
        )
        return result.scalar_one_or_none()

    async def get_catalog_pricing_profile_by_code(self, code: str) -> CatalogPricingProfile | None:
        result = await self.session.execute(
            select(CatalogPricingProfile).where(CatalogPricingProfile.code == code)
        )
        return result.scalar_one_or_none()

    async def get_tenant_pricing_profile(
        self,
        pricing_profile_id: str,
        *,
        organization_id: str,
    ) -> PricingProfile | None:
        result = await self.session.execute(
            select(PricingProfile).where(
                PricingProfile.id == pricing_profile_id,
                PricingProfile.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_tenant_work_type_setting(
        self,
        *,
        existing: TenantWorkTypeSetting | None,
        setting_id: str,
        organization_id: str,
        work_type_id: str,
        status: str,
        custom_display_name: str | None,
        analysis_profile_id: str | None,
        catalog_pricing_profile_id: str | None,
        tenant_pricing_profile_id: str | None,
        is_billable_override: bool | None,
        sort_order_override: int | None,
        updated_by_user_id: str | None,
    ) -> TenantWorkTypeSetting:
        if existing is None:
            setting = TenantWorkTypeSetting(
                id=setting_id,
                organization_id=organization_id,
                work_type_id=work_type_id,
                status=status,
                custom_display_name=custom_display_name,
                analysis_profile_id=analysis_profile_id,
                catalog_pricing_profile_id=catalog_pricing_profile_id,
                tenant_pricing_profile_id=tenant_pricing_profile_id,
                is_billable_override=is_billable_override,
                sort_order_override=sort_order_override,
                config_version=1,
                updated_by_user_id=updated_by_user_id,
            )
            self.session.add(setting)
        else:
            setting = existing
            setting.status = status
            setting.custom_display_name = custom_display_name
            setting.analysis_profile_id = analysis_profile_id
            setting.catalog_pricing_profile_id = catalog_pricing_profile_id
            setting.tenant_pricing_profile_id = tenant_pricing_profile_id
            setting.is_billable_override = is_billable_override
            setting.sort_order_override = sort_order_override
            setting.updated_by_user_id = updated_by_user_id
            setting.config_version = (setting.config_version or 0) + 1

        await self.session.commit()
        await self.session.refresh(setting)
        return setting

    async def upsert_tenant_parameter_overrides(
        self,
        *,
        tenant_work_type_setting: TenantWorkTypeSetting,
        overrides_payload: list[dict],
    ) -> list[TenantWorkTypeParameterOverride]:
        existing_rows_result = await self.session.execute(
            select(TenantWorkTypeParameterOverride).where(
                TenantWorkTypeParameterOverride.tenant_work_type_setting_id == tenant_work_type_setting.id
            )
        )
        existing_by_parameter_id = {
            row.work_type_parameter_id: row
            for row in existing_rows_result.scalars().all()
        }
        rows: list[TenantWorkTypeParameterOverride] = []
        for payload in overrides_payload:
            existing = existing_by_parameter_id.get(payload["work_type_parameter_id"])
            if existing is None:
                row = TenantWorkTypeParameterOverride(
                    id=payload["id"],
                    tenant_work_type_setting_id=tenant_work_type_setting.id,
                    organization_id=tenant_work_type_setting.organization_id,
                    work_type_id=tenant_work_type_setting.work_type_id,
                    work_type_parameter_id=payload["work_type_parameter_id"],
                    override_status=payload["override_status"],
                    custom_display_name=payload["custom_display_name"],
                    sort_order_override=payload["sort_order_override"],
                    default_text_value=payload["default_text_value"],
                    default_number_value=payload["default_number_value"],
                    default_boolean_value=payload["default_boolean_value"],
                    default_option_code=payload["default_option_code"],
                    config_version=1,
                    updated_by_user_id=payload["updated_by_user_id"],
                )
                self.session.add(row)
            else:
                row = existing
                row.override_status = payload["override_status"]
                row.custom_display_name = payload["custom_display_name"]
                row.sort_order_override = payload["sort_order_override"]
                row.default_text_value = payload["default_text_value"]
                row.default_number_value = payload["default_number_value"]
                row.default_boolean_value = payload["default_boolean_value"]
                row.default_option_code = payload["default_option_code"]
                row.updated_by_user_id = payload["updated_by_user_id"]
                row.config_version = (row.config_version or 0) + 1
            rows.append(row)

        await self.session.commit()
        for row in rows:
            await self.session.refresh(row)
        return rows

    async def list_project_work_items(
        self,
        project_id: str,
        *,
        organization_id: str,
    ) -> Sequence[ProjectWorkItem]:
        result = await self.session.execute(
            select(ProjectWorkItem)
            .options(
                selectinload(ProjectWorkItem.values).selectinload(ProjectWorkItemValue.parameter),
                selectinload(ProjectWorkItem.detections),
            )
            .where(
                ProjectWorkItem.project_id == project_id,
                ProjectWorkItem.organization_id == organization_id,
            )
            .order_by(
                ProjectWorkItem.item_sequence.asc(),
                ProjectWorkItem.created_at.asc(),
                ProjectWorkItem.id.asc(),
            )
        )
        return result.scalars().all()

    async def get_project_work_item(
        self,
        project_id: str,
        project_work_item_id: str,
        *,
        organization_id: str,
    ) -> ProjectWorkItem | None:
        result = await self.session.execute(
            select(ProjectWorkItem)
            .options(
                selectinload(ProjectWorkItem.values).selectinload(ProjectWorkItemValue.parameter),
                selectinload(ProjectWorkItem.detections),
            )
            .where(
                ProjectWorkItem.id == project_work_item_id,
                ProjectWorkItem.project_id == project_id,
                ProjectWorkItem.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_next_item_sequence(self, project_id: str, work_type_id: str) -> int:
        result = await self.session.execute(
            select(func.max(ProjectWorkItem.item_sequence)).where(
                ProjectWorkItem.project_id == project_id,
                ProjectWorkItem.work_type_id == work_type_id,
            )
        )
        return int(result.scalar_one() or 0) + 1

    async def create_project_work_item(
        self,
        *,
        work_item: ProjectWorkItem,
    ) -> ProjectWorkItem:
        self.session.add(work_item)
        await self.session.commit()
        return await self.get_project_work_item(
            work_item.project_id,
            work_item.id,
            organization_id=work_item.organization_id,
        )  # type: ignore[return-value]

    async def replace_project_work_item_values(
        self,
        *,
        project_work_item: ProjectWorkItem,
        values: list[ProjectWorkItemValue],
    ) -> ProjectWorkItem:
        project_work_item.values.clear()
        project_work_item.values.extend(values)
        await self.session.commit()
        return await self.get_project_work_item(
            project_work_item.project_id,
            project_work_item.id,
            organization_id=project_work_item.organization_id,
        )  # type: ignore[return-value]

    async def create_vision_detection(self, detection: VisionDetection) -> VisionDetection:
        self.session.add(detection)
        await self.session.commit()
        await self.session.refresh(detection)
        return detection

    @staticmethod
    def serialize_geometry(geometry: object | None) -> str | None:
        if geometry is None:
            return None
        return json.dumps(geometry, ensure_ascii=False)
