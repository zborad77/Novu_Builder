from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy import event

from app.core.cache import _k
from app.db.bootstrap import _seed_global_work_catalog
from app.repositories.work_catalog_repository import WorkCatalogRepository
from app.schemas.work_catalog import TenantWorkTypeSettingWithParametersUpsert
from app.services.analysis_profile_service import AnalysisProfileService
from app.services.pricing_profile_service import PricingProfileService
from app.services.tenant_work_type_resolution_service import TenantWorkTypeResolutionService
from app.services.work_catalog_service import WorkCatalogService
from app.work_catalog.cache import tenant_effective_cache_keys
from tests.test_work_catalog_core_subsystem import _ensure_global_catalog_seed, _ensure_tenant_setting


class _StatementCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def _before_cursor_execute(self, *args, **kwargs):
        self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, exc_type, exc, tb):
        event.remove(self.engine, "before_cursor_execute", self._before_cursor_execute)


async def test_global_work_catalog_seed_bootstrap_smoke(db_session):
    await _seed_global_work_catalog(db_session)
    await db_session.commit()

    repository = WorkCatalogRepository(db_session)
    categories = await repository.list_categories()
    work_types = await repository.list_work_types()

    assert categories
    assert work_types
    assert any(work_type.code == "roof-repair" for work_type in work_types)


async def test_effective_resolution_memoizes_repeated_reads_within_service_instance(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    repository = WorkCatalogRepository(db_session)
    service = TenantWorkTypeResolutionService(repository)

    counters = {
        "work_type": 0,
        "settings": 0,
        "overrides": 0,
        "extra_parameters": 0,
    }

    original_get_work_type = repository.get_work_type_by_code_for_resolution
    original_list_settings = repository.list_tenant_settings_for_resolution_for_org
    original_list_overrides = repository.list_parameter_overrides_for_org
    original_list_extra = repository.list_tenant_extra_parameters_for_org

    async def counted_get_work_type(*args, **kwargs):
        counters["work_type"] += 1
        return await original_get_work_type(*args, **kwargs)

    async def counted_list_settings(*args, **kwargs):
        counters["settings"] += 1
        return await original_list_settings(*args, **kwargs)

    async def counted_list_overrides(*args, **kwargs):
        counters["overrides"] += 1
        return await original_list_overrides(*args, **kwargs)

    async def counted_list_extra(*args, **kwargs):
        counters["extra_parameters"] += 1
        return await original_list_extra(*args, **kwargs)

    repository.get_work_type_by_code_for_resolution = counted_get_work_type
    repository.list_tenant_settings_for_resolution_for_org = counted_list_settings
    repository.list_parameter_overrides_for_org = counted_list_overrides
    repository.list_tenant_extra_parameters_for_org = counted_list_extra

    first = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )
    second = await service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert first.work_type.code == "roof-repair"
    assert second.work_type.code == "roof-repair"
    assert counters == {
        "work_type": 1,
        "settings": 1,
        "overrides": 1,
        "extra_parameters": 1,
    }


async def test_analysis_and_pricing_profile_resolution_memoize_hot_reads(
    db_session,
    test_tenants,
):
    await _ensure_global_catalog_seed(db_session)
    repository = WorkCatalogRepository(db_session)
    analysis_service = AnalysisProfileService(repository)
    pricing_service = PricingProfileService(repository)

    analysis_counter = 0
    pricing_counter = 0

    original_analysis_resolve = analysis_service.resolution_service.resolve_for_work_type
    original_pricing_resolve = pricing_service.resolution_service.resolve_for_work_type

    async def counted_analysis_resolve(*args, **kwargs):
        nonlocal analysis_counter
        analysis_counter += 1
        return await original_analysis_resolve(*args, **kwargs)

    async def counted_pricing_resolve(*args, **kwargs):
        nonlocal pricing_counter
        pricing_counter += 1
        return await original_pricing_resolve(*args, **kwargs)

    analysis_service.resolution_service.resolve_for_work_type = counted_analysis_resolve
    pricing_service.resolution_service.resolve_for_work_type = counted_pricing_resolve

    first_analysis = await analysis_service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )
    second_analysis = await analysis_service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )
    first_pricing = await pricing_service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )
    second_pricing = await pricing_service.resolve_for_work_type(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
    )

    assert first_analysis.profile_code == second_analysis.profile_code == "roof-repair-vision"
    assert first_pricing.profile_code == second_pricing.profile_code == "roof-repair-pricing"
    assert analysis_counter == 1
    assert pricing_counter == 1


async def test_effective_resolution_batches_profile_detail_loading_once_per_resolution_pass(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    repository = WorkCatalogRepository(db_session)
    service = TenantWorkTypeResolutionService(repository)

    counters = {
        "work_types_for_resolution": 0,
        "tenant_settings_for_resolution": 0,
        "analysis_profiles_by_ids": 0,
        "catalog_pricing_profiles_by_ids": 0,
    }

    original_list_work_types_for_resolution = repository.list_work_types_for_resolution
    original_list_tenant_settings_for_resolution_for_org = repository.list_tenant_settings_for_resolution_for_org
    original_list_analysis_profiles_by_ids = repository.list_analysis_profiles_by_ids
    original_list_catalog_pricing_profiles_by_ids = repository.list_catalog_pricing_profiles_by_ids

    async def counted_list_work_types_for_resolution(*args, **kwargs):
        counters["work_types_for_resolution"] += 1
        return await original_list_work_types_for_resolution(*args, **kwargs)

    async def counted_list_tenant_settings_for_resolution_for_org(*args, **kwargs):
        counters["tenant_settings_for_resolution"] += 1
        return await original_list_tenant_settings_for_resolution_for_org(*args, **kwargs)

    async def counted_list_analysis_profiles_by_ids(*args, **kwargs):
        counters["analysis_profiles_by_ids"] += 1
        return await original_list_analysis_profiles_by_ids(*args, **kwargs)

    async def counted_list_catalog_pricing_profiles_by_ids(*args, **kwargs):
        counters["catalog_pricing_profiles_by_ids"] += 1
        return await original_list_catalog_pricing_profiles_by_ids(*args, **kwargs)

    repository.list_work_types_for_resolution = counted_list_work_types_for_resolution
    repository.list_tenant_settings_for_resolution_for_org = counted_list_tenant_settings_for_resolution_for_org
    repository.list_analysis_profiles_by_ids = counted_list_analysis_profiles_by_ids
    repository.list_catalog_pricing_profiles_by_ids = counted_list_catalog_pricing_profiles_by_ids

    resolved = await service.resolve_all_for_org(organization_id=test_tenants["org_a"])

    assert resolved
    assert counters == {
        "work_types_for_resolution": 1,
        "tenant_settings_for_resolution": 1,
        "analysis_profiles_by_ids": 1,
        "catalog_pricing_profiles_by_ids": 1,
    }


async def test_effective_resolution_all_for_org_stays_under_query_ceiling(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    repository = WorkCatalogRepository(db_session)
    service = TenantWorkTypeResolutionService(repository)
    engine = db_session.bind.sync_engine

    with _StatementCounter(engine) as counter:
        resolved = await service.resolve_all_for_org(organization_id=test_tenants["org_a"])

    assert resolved
    assert counter.count <= 24


async def test_tenant_setting_write_invalidates_tenant_effective_cache_keys(
    db_session,
    test_tenants,
):
    await _ensure_tenant_setting(db_session, test_tenants)
    redis = AsyncMock()
    service = WorkCatalogService(WorkCatalogRepository(db_session), redis=redis)

    await service.upsert_tenant_setting(
        organization_id=test_tenants["org_a"],
        work_type_code="roof-repair",
        payload=TenantWorkTypeSettingWithParametersUpsert(
            status="enabled",
            customDisplayName="Tenant A Hardened Cache Name",
        ),
        updated_by_user_id="usr_e2e_a1",
    )

    deleted_keys = set(redis.delete.await_args.args)
    expected_keys = {
        _k(key)
        for key in tenant_effective_cache_keys(
            organization_id=test_tenants["org_a"],
            work_type_codes={"roof-repair"},
        )
    }
    assert expected_keys.issubset(deleted_keys)
