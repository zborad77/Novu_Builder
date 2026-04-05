from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes.material_catalog import (
    list_material_catalog,
    list_supplier_prices,
    patch_material,
)
from app.schemas.material_catalog import MaterialCatalogPatch


def _make_user(*, is_superadmin: bool, org_id: str | None):
    return SimpleNamespace(
        id="usr_test",
        organizationId=org_id,
        isSuperAdmin=is_superadmin,
        impersonatedBy=None,
    )


def _make_material_read(*, material_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=material_id,
        model_dump=lambda: {"id": material_id},
    )


class TestMaterialCatalogRouteTenantResolution:
    @pytest.mark.asyncio
    async def test_list_material_catalog_passes_resolved_org_id_for_tenant_user(self):
        current_user = _make_user(is_superadmin=False, org_id="org_abc")
        service = MagicMock()
        service.list_material_catalog = AsyncMock(return_value=[_make_material_read(material_id="mat_1")])

        response = await list_material_catalog.__wrapped__(
            request=MagicMock(),
            search="roof",
            includeInactive=False,
            current_user=current_user,
            service=service,
        )

        service.list_material_catalog.assert_awaited_once_with(
            organization_id="org_abc",
            search="roof",
            include_inactive=False,
        )
        assert response == {"items": [{"id": "mat_1"}], "total": 1}

    @pytest.mark.asyncio
    async def test_list_material_catalog_passes_none_for_superadmin_per_resolve_org_id_contract(self):
        current_user = _make_user(is_superadmin=True, org_id=None)
        service = MagicMock()
        service.list_material_catalog = AsyncMock(return_value=[])

        response = await list_material_catalog.__wrapped__(
            request=MagicMock(),
            search=None,
            includeInactive=True,
            current_user=current_user,
            service=service,
        )

        service.list_material_catalog.assert_awaited_once_with(
            organization_id=None,
            search=None,
            include_inactive=True,
        )
        assert response == {"items": [], "total": 0}

    @pytest.mark.asyncio
    async def test_list_supplier_prices_passes_resolved_org_id(self):
        current_user = _make_user(is_superadmin=False, org_id="org_abc")
        service = MagicMock()
        service.list_supplier_prices = AsyncMock(return_value=[_make_material_read(material_id="price_1")])

        response = await list_supplier_prices.__wrapped__(
            material_id="mat_1",
            request=MagicMock(),
            current_user=current_user,
            service=service,
        )

        service.list_supplier_prices.assert_awaited_once_with("mat_1", "org_abc")
        assert response == {"items": [{"id": "price_1"}], "total": 1}

    @pytest.mark.asyncio
    async def test_patch_material_passes_resolved_org_id_and_normalized_notes(self):
        current_user = _make_user(is_superadmin=False, org_id="org_abc")
        service = MagicMock()
        service.update_material = AsyncMock(return_value=_make_material_read(material_id="mat_1"))
        payload = MaterialCatalogPatch(
            defaultUnitPrice=123.0,
            defaultSupplierId="sup_1",
            notes="  trimmed note  ",
        )

        response = await patch_material(
            material_id="mat_1",
            payload=payload,
            current_user=current_user,
            service=service,
        )

        service.update_material.assert_awaited_once_with(
            "mat_1",
            "org_abc",
            default_unit_price=123.0,
            default_supplier_id="sup_1",
            notes="trimmed note",
        )
        assert response == {"id": "mat_1"}

    def test_source_uses_resolve_org_id_in_all_material_catalog_handlers(self):
        import inspect
        import app.api.routes.material_catalog as material_catalog_module

        source = inspect.getsource(material_catalog_module)

        assert source.count("resolve_org_id(current_user)") == 3
        assert "organization_id=current_user.organizationId" not in source
        assert "current_user.organizationId," not in source
