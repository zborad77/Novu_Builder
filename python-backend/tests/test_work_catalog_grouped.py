import pytest

from tests.test_work_catalog_core_subsystem import _ensure_global_catalog_seed

_EXPECTED_GROUP_CODES = [
    "masonry-structural",
    "roofing",
    "exterior-works",
    "demolition-finishing-utilities",
]

_EXPECTED_GROUP_NAMES = {
    "masonry-structural": "Zednické a konstrukční práce",
    "roofing": "Střešní práce",
    "exterior-works": "Exteriérové práce",
    "demolition-finishing-utilities": "Další stavební práce",
}


@pytest.mark.asyncio
async def test_grouped_catalog_returns_four_groups_with_czech_names(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    await _ensure_global_catalog_seed(db_session)
    headers = {"Authorization": f"Bearer {token_a}"}

    response = await app_client.get("/api/v1/work-catalog/catalog/grouped", headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    assert "items" in body
    assert "total" in body

    items = body["items"]
    assert len(items) == 4

    codes = [item["code"] for item in items]
    assert codes == _EXPECTED_GROUP_CODES, f"Unexpected group order: {codes}"

    for item in items:
        code = item["code"]
        assert item["name"] == _EXPECTED_GROUP_NAMES[code], (
            f"Group '{code}': expected '{_EXPECTED_GROUP_NAMES[code]}', got '{item['name']}'"
        )
        assert isinstance(item["types"], list)
        assert len(item["types"]) > 0, f"Group '{code}' has no work types"
        for wt in item["types"]:
            assert "code" in wt
            assert "name" in wt
            assert wt["name"], f"Work type '{wt['code']}' has empty name"

    total = sum(len(item["types"]) for item in items)
    assert body["total"] == total


@pytest.mark.asyncio
async def test_grouped_catalog_roofing_contains_roof_repair(
    app_client,
    db_session,
    test_tenants,
    token_a,
):
    await _ensure_global_catalog_seed(db_session)
    headers = {"Authorization": f"Bearer {token_a}"}

    response = await app_client.get("/api/v1/work-catalog/catalog/grouped", headers=headers)
    assert response.status_code == 200, response.text

    roofing = next(item for item in response.json()["items"] if item["code"] == "roofing")
    codes = [wt["code"] for wt in roofing["types"]]
    assert "roof-repair" in codes

    roof_repair = next(wt for wt in roofing["types"] if wt["code"] == "roof-repair")
    assert roof_repair["name"] == "Oprava střechy"


@pytest.mark.asyncio
async def test_grouped_catalog_requires_auth(app_client, db_session, test_tenants):
    await _ensure_global_catalog_seed(db_session)

    response = await app_client.get("/api/v1/work-catalog/catalog/grouped")
    assert response.status_code == 401
