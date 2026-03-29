from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models import MaterialCatalog, PricingProfile, Project, Supplier


async def _seed_list_stability_rows(db_session, test_tenants):
    token = uuid4().hex[:8]
    base = datetime.now(UTC) + timedelta(days=7)

    project_ids = {
        "newest": f"prj_lst_{token}_003",
        "tie_high": f"prj_lst_{token}_002",
        "tie_low": f"prj_lst_{token}_001",
        "other_org": f"prj_lst_{token}_900",
    }
    supplier_ids = {
        "alpha": f"sup_lst_{token}_a",
        "inactive": f"sup_lst_{token}_m",
        "zulu": f"sup_lst_{token}_z",
        "other_org": f"sup_lst_{token}_b",
    }
    material_ids = {
        "alpha": f"mat_lst_{token}_a",
        "inactive": f"mat_lst_{token}_m",
        "zulu": f"mat_lst_{token}_z",
        "other_org": f"mat_lst_{token}_b",
    }
    pricebook_ids = {
        "alpha": f"pb_lst_{token}_a",
        "zulu": f"pb_lst_{token}_z",
        "other_org": f"pb_lst_{token}_b",
    }

    db_session.add_all(
        [
            Project(
                id=project_ids["newest"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"List Stability {token} newest",
                description=f"List stability marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=3),
                updated_at=base + timedelta(minutes=3),
            ),
            Project(
                id=project_ids["tie_high"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"List Stability {token} tie high",
                description=f"List stability marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=2),
                updated_at=base + timedelta(minutes=2),
            ),
            Project(
                id=project_ids["tie_low"],
                organization_id=test_tenants["org_a"],
                created_by_user_id="usr_e2e_a1",
                title=f"List Stability {token} tie low",
                description=f"List stability marker {token}",
                status="archived",
                source="mobile",
                created_at=base + timedelta(minutes=2),
                updated_at=base + timedelta(minutes=2),
            ),
            Project(
                id=project_ids["other_org"],
                organization_id=test_tenants["org_b"],
                created_by_user_id="usr_e2e_b1",
                title=f"List Stability {token} foreign",
                description=f"List stability marker {token}",
                status="draft",
                source="mobile",
                created_at=base + timedelta(minutes=4),
                updated_at=base + timedelta(minutes=4),
            ),
            Supplier(
                id=supplier_ids["alpha"],
                organization_id=test_tenants["org_a"],
                name=f"Alpha Supplier {token}",
                integration_type="manual",
                is_active=True,
            ),
            Supplier(
                id=supplier_ids["inactive"],
                organization_id=test_tenants["org_a"],
                name=f"Middle Supplier {token}",
                integration_type="manual",
                is_active=False,
            ),
            Supplier(
                id=supplier_ids["zulu"],
                organization_id=test_tenants["org_a"],
                name=f"Zulu Supplier {token}",
                integration_type="manual",
                is_active=True,
            ),
            Supplier(
                id=supplier_ids["other_org"],
                organization_id=test_tenants["org_b"],
                name=f"Alpha Supplier {token} Foreign",
                integration_type="manual",
                is_active=True,
            ),
            MaterialCatalog(
                id=material_ids["alpha"],
                organization_id=test_tenants["org_a"],
                name=f"Alpha Material {token}",
                unit="m2",
                norm_per_sqm=1.0,
                default_unit_price=100.0,
                is_active=True,
            ),
            MaterialCatalog(
                id=material_ids["inactive"],
                organization_id=test_tenants["org_a"],
                name=f"Middle Material {token}",
                unit="m2",
                norm_per_sqm=1.0,
                default_unit_price=110.0,
                is_active=False,
            ),
            MaterialCatalog(
                id=material_ids["zulu"],
                organization_id=test_tenants["org_a"],
                name=f"Zulu Material {token}",
                unit="m2",
                norm_per_sqm=1.0,
                default_unit_price=120.0,
                is_active=True,
            ),
            MaterialCatalog(
                id=material_ids["other_org"],
                organization_id=test_tenants["org_b"],
                name=f"Alpha Material {token} Foreign",
                unit="m2",
                norm_per_sqm=1.0,
                default_unit_price=130.0,
                is_active=True,
            ),
            PricingProfile(
                id=pricebook_ids["alpha"],
                organization_id=test_tenants["org_a"],
                name=f"Alpha Pricebook {token}",
                hourly_rate=310.0,
                daily_rate=2480.0,
                labor_hours_per_sqm=0.3,
                margin_economy_pct=10.0,
                margin_standard_pct=18.0,
                margin_premium_pct=28.0,
                vat_pct=21.0,
                currency="CZK",
                is_default=False,
            ),
            PricingProfile(
                id=pricebook_ids["zulu"],
                organization_id=test_tenants["org_a"],
                name=f"Zulu Pricebook {token}",
                hourly_rate=320.0,
                daily_rate=2560.0,
                labor_hours_per_sqm=0.3,
                margin_economy_pct=10.0,
                margin_standard_pct=18.0,
                margin_premium_pct=28.0,
                vat_pct=21.0,
                currency="CZK",
                is_default=False,
            ),
            PricingProfile(
                id=pricebook_ids["other_org"],
                organization_id=test_tenants["org_b"],
                name=f"Alpha Pricebook {token} Foreign",
                hourly_rate=330.0,
                daily_rate=2640.0,
                labor_hours_per_sqm=0.3,
                margin_economy_pct=10.0,
                margin_standard_pct=18.0,
                margin_premium_pct=28.0,
                vat_pct=21.0,
                currency="CZK",
                is_default=False,
            ),
        ]
    )
    await db_session.commit()

    return {
        "token": token,
        "projects": project_ids,
        "suppliers": supplier_ids,
        "materials": material_ids,
        "pricebooks": pricebook_ids,
    }


async def test_cases_list_runtime_filters_ordering_and_tenant_scoping_are_stable(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    seeded = await _seed_list_stability_rows(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}

    response = await app_client.get(
        "/api/v1/cases",
        params={
            "status": "draft",
            "search": seeded["token"],
            "limit": 10,
            "org_id": test_tenants["org_b"],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text

    items = response.json()["items"]
    ids = [item["id"] for item in items if seeded["token"] in item["title"]]

    assert ids == [
        seeded["projects"]["newest"],
        seeded["projects"]["tie_high"],
    ]
    assert seeded["projects"]["tie_low"] not in ids
    assert seeded["projects"]["other_org"] not in ids


async def test_cases_list_cursor_and_limit_are_stable_and_non_overlapping(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    seeded = await _seed_list_stability_rows(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}
    params = {"search": seeded["token"], "limit": 2}

    first_page = await app_client.get("/api/v1/cases", params=params, headers=headers)
    assert first_page.status_code == 200, first_page.text

    first_body = first_page.json()
    first_ids = [item["id"] for item in first_body["items"] if seeded["token"] in item["title"]]
    assert first_ids == [
        seeded["projects"]["newest"],
        seeded["projects"]["tie_high"],
    ]
    assert first_body["next_cursor"]

    second_page = await app_client.get(
        "/api/v1/cases",
        params={**params, "cursor": first_body["next_cursor"]},
        headers=headers,
    )
    assert second_page.status_code == 200, second_page.text

    second_body = second_page.json()
    second_ids = [item["id"] for item in second_body["items"] if seeded["token"] in item["title"]]
    assert second_ids == [seeded["projects"]["tie_low"]]
    assert set(first_ids).isdisjoint(second_ids)


async def test_suppliers_list_include_inactive_and_ordering_are_stable(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    seeded = await _seed_list_stability_rows(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}

    active_only = await app_client.get("/api/v1/suppliers", headers=headers)
    assert active_only.status_code == 200, active_only.text

    active_ids = [
        item["id"]
        for item in active_only.json()["items"]
        if item["id"] in seeded["suppliers"].values()
    ]
    assert active_ids == [
        seeded["suppliers"]["alpha"],
        seeded["suppliers"]["zulu"],
    ]
    assert seeded["suppliers"]["inactive"] not in active_ids
    assert seeded["suppliers"]["other_org"] not in active_ids

    include_inactive = await app_client.get(
        "/api/v1/suppliers",
        params={"includeInactive": "true"},
        headers=headers,
    )
    assert include_inactive.status_code == 200, include_inactive.text

    all_ids = [
        item["id"]
        for item in include_inactive.json()["items"]
        if item["id"] in seeded["suppliers"].values()
    ]
    assert all_ids == [
        seeded["suppliers"]["alpha"],
        seeded["suppliers"]["inactive"],
        seeded["suppliers"]["zulu"],
    ]
    assert seeded["suppliers"]["other_org"] not in all_ids


async def test_material_catalog_search_include_inactive_and_ordering_are_stable(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    seeded = await _seed_list_stability_rows(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}

    active_only = await app_client.get(
        "/api/v1/material-catalog",
        params={"search": seeded["token"]},
        headers=headers,
    )
    assert active_only.status_code == 200, active_only.text

    active_ids = [item["id"] for item in active_only.json()["items"]]
    assert active_ids == [
        seeded["materials"]["alpha"],
        seeded["materials"]["zulu"],
    ]
    assert seeded["materials"]["inactive"] not in active_ids
    assert seeded["materials"]["other_org"] not in active_ids

    include_inactive = await app_client.get(
        "/api/v1/material-catalog",
        params={"search": seeded["token"], "includeInactive": "true"},
        headers=headers,
    )
    assert include_inactive.status_code == 200, include_inactive.text

    all_ids = [item["id"] for item in include_inactive.json()["items"]]
    assert all_ids == [
        seeded["materials"]["alpha"],
        seeded["materials"]["inactive"],
        seeded["materials"]["zulu"],
    ]
    assert seeded["materials"]["other_org"] not in all_ids


async def test_pricebooks_list_is_tenant_scoped_and_default_first(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    seeded = await _seed_list_stability_rows(db_session, test_tenants)
    headers = {"Authorization": f"Bearer {token_a}"}

    response = await app_client.get("/api/v1/pricebooks", headers=headers)
    assert response.status_code == 200, response.text

    items = response.json()["items"]
    ids = [item["id"] for item in items]
    seeded_ids = [item["id"] for item in items if item["id"] in seeded["pricebooks"].values()]

    assert seeded_ids == [
        seeded["pricebooks"]["alpha"],
        seeded["pricebooks"]["zulu"],
    ]
    assert seeded["pricebooks"]["other_org"] not in ids
    assert ids.index(test_tenants["pricebook_a"]) < ids.index(seeded["pricebooks"]["alpha"])
