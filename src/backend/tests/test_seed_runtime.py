from __future__ import annotations

from uuid import uuid4

from app.db.bootstrap import _seed_global_work_catalog
from app.db.seed_runtime import (
    SeedModelPlan,
    SeedWriteMode,
    apply_seed_model_plan,
)
from app.models import WorkCategory


async def test_authoritative_upsert_updates_existing_seeded_row_and_reports_delta(db_session):
    category_id = f"wc_seed_rt_{uuid4().hex[:8]}"
    db_session.add(
        WorkCategory(
            id=category_id,
            code=f"seed-rt-{uuid4().hex[:6]}",
            slug=f"seed-rt-{uuid4().hex[:6]}",
            name="Old Name",
            description="old",
            sort_order=10,
            is_active=True,
            catalog_version=1,
        )
    )
    await db_session.commit()

    plan = SeedModelPlan(
        name="test_categories",
        model=WorkCategory,
        rows=[
            {
                "id": category_id,
                "code": f"seed-rt-{uuid4().hex[:6]}",
                "slug": f"seed-rt-{uuid4().hex[:6]}",
                "name": "New Name",
                "description": "new",
                "sort_order": 20,
                "is_active": True,
                "catalog_version": 2,
            }
        ],
        mode=SeedWriteMode.AUTHORITATIVE_UPSERT,
    )

    report = await apply_seed_model_plan(db_session, plan)
    await db_session.commit()

    refreshed = await db_session.get(WorkCategory, category_id)
    assert refreshed is not None
    assert refreshed.name == "New Name"
    assert refreshed.description == "new"
    assert refreshed.sort_order == 20
    assert refreshed.catalog_version == 2
    assert report.inserted == 0
    assert report.updated == 1
    assert report.unchanged == 0
    assert report.skipped == 0


async def test_insert_if_absent_skips_existing_row_without_mutation(db_session):
    category_id = f"wc_seed_skip_{uuid4().hex[:8]}"
    original_code = f"seed-skip-{uuid4().hex[:6]}"
    db_session.add(
        WorkCategory(
            id=category_id,
            code=original_code,
            slug=original_code,
            name="Stable Name",
            description="original",
            sort_order=10,
            is_active=True,
            catalog_version=1,
        )
    )
    await db_session.commit()

    plan = SeedModelPlan(
        name="test_categories_insert_only",
        model=WorkCategory,
        rows=[
            {
                "id": category_id,
                "code": f"seed-skip-{uuid4().hex[:6]}",
                "slug": f"seed-skip-{uuid4().hex[:6]}",
                "name": "Mutated Name",
                "description": "mutated",
                "sort_order": 99,
                "is_active": False,
                "catalog_version": 9,
            }
        ],
        mode=SeedWriteMode.INSERT_IF_ABSENT,
    )

    report = await apply_seed_model_plan(db_session, plan)
    await db_session.commit()

    refreshed = await db_session.get(WorkCategory, category_id)
    assert refreshed is not None
    assert refreshed.code == original_code
    assert refreshed.name == "Stable Name"
    assert refreshed.description == "original"
    assert refreshed.sort_order == 10
    assert refreshed.catalog_version == 1
    assert report.inserted == 0
    assert report.updated == 0
    assert report.unchanged == 0
    assert report.skipped == 1


async def test_global_work_catalog_seed_is_idempotent_on_second_run(db_session):
    await _seed_global_work_catalog(db_session)
    await db_session.commit()

    second_report = await _seed_global_work_catalog(db_session)
    await db_session.commit()

    assert second_report.inserted == 0
    assert second_report.updated == 0
    assert second_report.unchanged > 0
    assert second_report.skipped == 0
