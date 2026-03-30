from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models import MaterialCatalog, PricingProfile, Project, ProjectPhoto, Supplier
from app.repositories.photo_repository import PhotoRepository
from app.repositories.pricebook_repository import PricebookRepository
from app.repositories.material_catalog_repository import MaterialCatalogRepository
from app.services.material_catalog_service import MaterialCatalogService


async def _seed_photo_flags(db_session, test_tenants):
    token = uuid4().hex[:8]
    base = datetime.now(UTC) + timedelta(days=30)
    project_a = f"prj_qh_{token}_a"
    project_b = f"prj_qh_{token}_b"
    db_session.add_all(
        [
            Project(
                id=project_a,
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"Query hardening A {token}",
                status="draft",
                source="mobile",
                created_at=base,
                updated_at=base,
            ),
            Project(
                id=project_b,
                organization_id=test_tenants["org_b"],
                created_by_user_id="usr_e2e_b1",
                title=f"Query hardening B {token}",
                status="draft",
                source="mobile",
                created_at=base,
                updated_at=base,
            ),
            ProjectPhoto(
                id=f"pho_qh_{token}_a1",
                project_id=project_a,
                storage_key=f"projects/{project_a}/a1.jpg",
                original_filename="a1.jpg",
                mime_type="image/jpeg",
                file_size=101,
                processing_status="ready",
                is_primary=True,
                is_analysis_reference=True,
                sort_order=1,
                created_at=base + timedelta(seconds=1),
            ),
            ProjectPhoto(
                id=f"pho_qh_{token}_a2",
                project_id=project_a,
                storage_key=f"projects/{project_a}/a2.jpg",
                original_filename="a2.jpg",
                mime_type="image/jpeg",
                file_size=102,
                processing_status="ready",
                is_primary=False,
                is_analysis_reference=False,
                sort_order=2,
                created_at=base + timedelta(seconds=2),
            ),
            ProjectPhoto(
                id=f"pho_qh_{token}_b1",
                project_id=project_b,
                storage_key=f"projects/{project_b}/b1.jpg",
                original_filename="b1.jpg",
                mime_type="image/jpeg",
                file_size=201,
                processing_status="ready",
                is_primary=True,
                is_analysis_reference=True,
                sort_order=1,
                created_at=base + timedelta(seconds=3),
            ),
        ]
    )
    await db_session.commit()
    return project_a, project_b


async def test_photo_repository_clear_primary_updates_only_target_project(db_session, test_tenants):
    project_a, project_b = await _seed_photo_flags(db_session, test_tenants)
    repo = PhotoRepository(db_session)

    await repo.clear_primary(project_a)
    await repo.save_changes()

    photos_a = list(await repo.list_photos_by_project_id(project_a))
    photos_b = list(await repo.list_photos_by_project_id(project_b))
    assert [photo.is_primary for photo in photos_a] == [False, False]
    assert [photo.is_primary for photo in photos_b] == [True]


async def test_photo_repository_clear_analysis_reference_updates_only_target_project(db_session, test_tenants):
    project_a, project_b = await _seed_photo_flags(db_session, test_tenants)
    repo = PhotoRepository(db_session)

    await repo.clear_analysis_reference(project_a)
    await repo.save_changes()

    photos_a = list(await repo.list_photos_by_project_id(project_a))
    photos_b = list(await repo.list_photos_by_project_id(project_b))
    assert [photo.is_analysis_reference for photo in photos_a] == [False, False]
    assert [photo.is_analysis_reference for photo in photos_b] == [True]


async def test_pricebook_repository_create_default_clears_existing_default_in_same_org_only(db_session, test_tenants):
    repo = PricebookRepository(db_session)
    token = uuid4().hex[:8]

    created = await repo.create_pricebook(
        {
            "name": f"Default replacement {token}",
            "hourlyRate": 555.0,
            "dailyRate": 4444.0,
            "laborHoursPerSqm": 0.45,
            "vatPct": 21.0,
            "currency": "CZK",
            "isDefault": True,
        },
        test_tenants["org_a"],
    )

    assert created.is_default is True

    pricebooks_a = await repo.list_pricebooks(test_tenants["org_a"])
    pricebooks_b = await repo.list_pricebooks(test_tenants["org_b"])
    defaults_a = [item.id for item in pricebooks_a if item.is_default]
    defaults_b = [item.id for item in pricebooks_b if item.is_default]

    assert defaults_a == [created.id]
    assert defaults_b == [test_tenants["pricebook_b"]]


async def test_material_catalog_service_uses_loaded_supplier_relation_for_listing(db_session, test_tenants, monkeypatch):
    token = uuid4().hex[:8]
    supplier = Supplier(
        id=f"sup_qh_{token}",
        organization_id=test_tenants["org_a"],
        name=f"Supplier {token}",
        integration_type="manual",
        is_active=True,
    )
    material = MaterialCatalog(
        id=f"mat_qh_{token}",
        organization_id=test_tenants["org_a"],
        name=f"Material {token}",
        unit="m2",
        norm_per_sqm=1.0,
        default_unit_price=111.0,
        default_supplier_id=supplier.id,
        is_active=True,
    )
    db_session.add_all([supplier, material])
    await db_session.commit()

    repo = MaterialCatalogRepository(db_session)
    service = MaterialCatalogService(repo)

    async def _unexpected_get_supplier_name(*args, **kwargs):
        raise AssertionError("list_material_catalog must not perform per-row supplier lookups")

    monkeypatch.setattr(repo, "get_supplier_name", _unexpected_get_supplier_name)

    items = await service.list_material_catalog(organization_id=test_tenants["org_a"], search=token)

    assert len(items) == 1
    assert items[0].id == material.id
    assert items[0].default_supplier_name == supplier.name


def test_hot_path_indexes_are_present_in_metadata():
    pricing_index_names = {index.name for index in PricingProfile.__table__.indexes}
    supplier_index_names = {index.name for index in Supplier.__table__.indexes}
    material_index_names = {index.name for index in MaterialCatalog.__table__.indexes}
    project_photo_index_names = {index.name for index in ProjectPhoto.__table__.indexes}

    assert "idx_pricing_profiles_org_default_name" in pricing_index_names
    assert "idx_suppliers_org_active_name" in supplier_index_names
    assert "idx_material_catalog_org_active_name" in material_index_names
    assert "idx_project_photos_project_sort_created" in project_photo_index_names
