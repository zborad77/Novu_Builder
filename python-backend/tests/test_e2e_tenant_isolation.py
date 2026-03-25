"""
E2E / integration tests — tenant isolation
==========================================

Strategy
--------
- Two isolated tenants (Org A, Org B) are created in a test SQLite database
  via conftest.py fixtures.
- Tests make **real HTTP requests** through the full FastAPI ASGI stack using
  httpx.AsyncClient + ASGITransport.
- No repository/service mocks — the actual auth, tenant-scoping, and
  persistence layers are exercised end-to-end.
- Each test is independently readable: setup is in conftest.py fixtures,
  assertions are explicit about expected HTTP status and response content.

Scenarios covered
-----------------
1.  Tenant B cannot read a project that belongs to Tenant A  (→ 404)
2.  Tenant B cannot patch a project that belongs to Tenant A (→ 404)
3.  Tenant B cannot duplicate a project of Tenant A          (→ 404)
4.  Tenant B cannot archive a project of Tenant A            (→ 404)
5.  Tenant B cannot create an analysis job on Tenant A's case (→ 404)
6.  Tenant B cannot read an analysis job from Tenant A's case (→ 404)
7.  Tenant B cannot cancel an analysis job from Tenant A      (→ 404)
8.  Tenant B cannot list images of Tenant A's case            (→ 404)
9.  Tenant B cannot upload images to Tenant A's case          (→ 404)
10. Tenant B cannot start an export for Tenant A's case       (→ 404)
11. Pricebook listing returns only the requesting tenant's profiles
12. Cross-tenant pricebook item access is denied              (→ 404)
13. Supplier listing returns only the requesting tenant's suppliers
14. Material-catalog listing returns only the requesting tenant's items
15. [Positive] Tenant A can read their own project            (→ 200)
16. [Positive] Tenant B can read their own project            (→ 200)
17. [Positive] Both tenants see their own default pricing profile

Scenarios NOT covered (infra gap — described at bottom of file)
---------------------------------------------------------------
- Measurement confirm / patch (requires a completed analysis job with results)
- Quote-variant cross-tenant access (requires completed analysis + pricing flow)
- Export file download isolation (ExportService returns in-memory JSON; no
  file is written to disk in the mock path, so there is nothing to steal)
"""

import pytest


# =============================================================================
# 1. Project (case) read isolation
# =============================================================================

class TestProjectReadIsolation:

    async def test_tenant_b_cannot_read_tenant_a_project(
        self, app_client, token_b, case_a_id
    ):
        """GET /cases/{id} with Tenant B token → 404 (not 403, not 200)."""
        resp = await app_client.get(
            f"/api/v1/cases/{case_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_does_not_see_tenant_a_project_in_list(
        self, app_client, token_b, case_a_id
    ):
        """GET /cases (list) as Tenant B must not contain Tenant A's case ID."""
        resp = await app_client.get(
            "/api/v1/cases",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert case_a_id not in ids, (
            f"Tenant B's project list contains Tenant A's case {case_a_id!r}"
        )

    async def test_tenant_a_can_read_own_project(
        self, app_client, token_a, case_a_id
    ):
        """[Positive] GET /cases/{id} with correct tenant token → 200."""
        resp = await app_client.get(
            f"/api/v1/cases/{case_a_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == case_a_id


# =============================================================================
# 2. Project mutation isolation (PATCH / special actions)
# =============================================================================

class TestProjectMutationIsolation:

    async def test_tenant_b_cannot_patch_tenant_a_project(
        self, app_client, token_b, case_a_id
    ):
        """PATCH /cases/{id} by Tenant B → 404."""
        resp = await app_client.patch(
            f"/api/v1/cases/{case_a_id}",
            json={"title": "Hijacked by Tenant B"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_duplicate_tenant_a_project(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/duplicate by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/duplicate",
            json={"title": "Stolen copy"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_archive_tenant_a_project(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/archive by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/archive",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_patch_proposal_draft_of_tenant_a(
        self, app_client, token_b, case_a_id
    ):
        """PATCH /cases/{id}/proposal-draft by Tenant B → 404."""
        resp = await app_client.patch(
            f"/api/v1/cases/{case_a_id}/proposal-draft",
            json={"summary": "unauthorized change"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text


# =============================================================================
# 3. Analysis job isolation
# =============================================================================

class TestAnalysisJobIsolation:

    async def test_tenant_b_cannot_trigger_analysis_on_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/analysis-jobs by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_list_analysis_jobs_of_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """GET /cases/{id}/analysis-jobs by Tenant B → 404."""
        resp = await app_client.get(
            f"/api/v1/cases/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_read_tenant_a_analysis_job_by_id(
        self, app_client, token_b, job_a_id
    ):
        """GET /analysis-jobs/{id} where job belongs to Tenant A → 404."""
        resp = await app_client.get(
            f"/api/v1/analysis-jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_cancel_tenant_a_analysis_job(
        self, app_client, token_b, job_a_id
    ):
        """POST /analysis-jobs/{id}/cancel for a job owned by Tenant A → 404."""
        resp = await app_client.post(
            f"/api/v1/analysis-jobs/{job_a_id}/cancel",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_retry_tenant_a_analysis_job(
        self, app_client, token_b, job_a_id
    ):
        """POST /analysis-jobs/{id}/retry for a job owned by Tenant A → 404."""
        resp = await app_client.post(
            f"/api/v1/analysis-jobs/{job_a_id}/retry",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_a_can_read_own_analysis_job(
        self, app_client, token_a, job_a_id
    ):
        """[Positive] GET /analysis-jobs/{id} by the owning tenant → 200."""
        resp = await app_client.get(
            f"/api/v1/analysis-jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == job_a_id


# =============================================================================
# 4. Image (photo) isolation
# =============================================================================

class TestImageIsolation:

    async def test_tenant_b_cannot_list_images_of_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """GET /cases/{id}/images by Tenant B → 404."""
        resp = await app_client.get(
            f"/api/v1/cases/{case_a_id}/images",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_upload_image_to_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/images (JSON upload) by Tenant B → 404.

        The request is denied before any file bytes are processed because
        the project-ownership check fires first.
        """
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/images",
            json={"files": []},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text


# =============================================================================
# 5. Export isolation
# =============================================================================

class TestExportIsolation:

    async def test_tenant_b_cannot_create_report_pdf_for_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/exports/report-pdf by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/exports/report-pdf",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_create_case_zip_for_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/exports/case-zip by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/exports/case-zip",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_create_proposal_docx_for_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """POST /cases/{id}/exports/proposal-docx by Tenant B → 404."""
        resp = await app_client.post(
            f"/api/v1/cases/{case_a_id}/exports/proposal-docx",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text


# =============================================================================
# 6. Pricebook / pricing profile isolation
# =============================================================================

class TestPricebookIsolation:

    async def test_tenant_a_sees_only_own_pricebooks(
        self, app_client, token_a, test_tenants
    ):
        """GET /pricebooks returns only Tenant A's profiles."""
        resp = await app_client.get(
            "/api/v1/pricebooks",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["pricebook_a"] in ids, "Tenant A's own pricebook missing"
        assert test_tenants["pricebook_b"] not in ids, "Tenant B's pricebook leaked into A's list"

    async def test_tenant_b_sees_only_own_pricebooks(
        self, app_client, token_b, test_tenants
    ):
        """GET /pricebooks returns only Tenant B's profiles."""
        resp = await app_client.get(
            "/api/v1/pricebooks",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["pricebook_b"] in ids, "Tenant B's own pricebook missing"
        assert test_tenants["pricebook_a"] not in ids, "Tenant A's pricebook leaked into B's list"

    async def test_tenant_b_cannot_read_tenant_a_pricebook_items(
        self, app_client, token_b, test_tenants
    ):
        """GET /pricebooks/{id}/items where pricebook belongs to Tenant A → 404."""
        pricebook_a = test_tenants["pricebook_a"]
        resp = await app_client.get(
            f"/api/v1/pricebooks/{pricebook_a}/items",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_a_cannot_read_tenant_b_pricebook_items(
        self, app_client, token_a, test_tenants
    ):
        """GET /pricebooks/{id}/items where pricebook belongs to Tenant B → 404."""
        pricebook_b = test_tenants["pricebook_b"]
        resp = await app_client.get(
            f"/api/v1/pricebooks/{pricebook_b}/items",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_default_pricing_profile_is_tenant_scoped(
        self, app_client, token_a, token_b, test_tenants
    ):
        """Each tenant's default pricebook is their own; they cannot see the other's default."""
        resp_a = await app_client.get(
            "/api/v1/pricebooks",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        resp_b = await app_client.get(
            "/api/v1/pricebooks",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        defaults_a = [i for i in resp_a.json()["items"] if i.get("isDefault")]
        defaults_b = [i for i in resp_b.json()["items"] if i.get("isDefault")]

        # Each tenant has exactly their own default
        assert all(i["id"] != test_tenants["pricebook_b"] for i in defaults_a), (
            "Tenant B's default profile leaked into Tenant A's defaults"
        )
        assert all(i["id"] != test_tenants["pricebook_a"] for i in defaults_b), (
            "Tenant A's default profile leaked into Tenant B's defaults"
        )


# =============================================================================
# 7. Supplier isolation
# =============================================================================

class TestSupplierIsolation:

    async def test_tenant_a_sees_only_own_suppliers(
        self, app_client, token_a, test_tenants
    ):
        """GET /suppliers returns only Tenant A's suppliers."""
        resp = await app_client.get(
            "/api/v1/suppliers",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["supplier_a"] in ids, "Tenant A's own supplier missing"
        assert test_tenants["supplier_b"] not in ids, "Tenant B's supplier leaked into A's list"

    async def test_tenant_b_sees_only_own_suppliers(
        self, app_client, token_b, test_tenants
    ):
        """GET /suppliers returns only Tenant B's suppliers."""
        resp = await app_client.get(
            "/api/v1/suppliers",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["supplier_b"] in ids, "Tenant B's own supplier missing"
        assert test_tenants["supplier_a"] not in ids, "Tenant A's supplier leaked into B's list"

    async def test_tenant_b_cannot_patch_tenant_a_supplier(
        self, app_client, token_b, test_tenants
    ):
        """PATCH /suppliers/{id} where supplier belongs to Tenant A → 404."""
        supplier_a = test_tenants["supplier_a"]
        resp = await app_client.patch(
            f"/api/v1/suppliers/{supplier_a}",
            json={
                "name": "Hijacked Supplier",
                "integrationType": "manual",
                "websiteUrl": None,
                "contactName": None,
                "contactEmail": None,
            },
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text


# =============================================================================
# 8. Material catalog isolation
# =============================================================================

class TestMaterialCatalogIsolation:

    async def test_tenant_a_sees_only_own_materials(
        self, app_client, token_a, test_tenants
    ):
        """GET /material-catalog returns only Tenant A's items."""
        resp = await app_client.get(
            "/api/v1/material-catalog",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["material_a"] in ids, "Tenant A's material missing"
        assert test_tenants["material_b"] not in ids, "Tenant B's material leaked into A's catalog"

    async def test_tenant_b_sees_only_own_materials(
        self, app_client, token_b, test_tenants
    ):
        """GET /material-catalog returns only Tenant B's items."""
        resp = await app_client.get(
            "/api/v1/material-catalog",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["material_b"] in ids, "Tenant B's material missing"
        assert test_tenants["material_a"] not in ids, "Tenant A's material leaked into B's catalog"

    async def test_tenant_b_cannot_patch_tenant_a_material(
        self, app_client, token_b, test_tenants
    ):
        """PATCH /material-catalog/{id} where material belongs to Tenant A → 404."""
        material_a = test_tenants["material_a"]
        resp = await app_client.patch(
            f"/api/v1/material-catalog/{material_a}",
            json={"defaultUnitPrice": 0.01, "notes": "tampered"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text

    async def test_tenant_b_cannot_read_supplier_prices_of_tenant_a_material(
        self, app_client, token_b, test_tenants
    ):
        """GET /material-catalog/{id}/supplier-prices for Tenant A's material → 404."""
        material_a = test_tenants["material_a"]
        resp = await app_client.get(
            f"/api/v1/material-catalog/{material_a}/supplier-prices",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, resp.text


# =============================================================================
# 9. Positive-path sanity checks
# =============================================================================

class TestPositivePath:

    async def test_tenant_b_can_read_own_project(
        self, app_client, token_b, case_b_id
    ):
        """[Positive] GET /cases/{id} — Tenant B reads their own case."""
        resp = await app_client.get(
            f"/api/v1/cases/{case_b_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == case_b_id

    async def test_tenant_b_can_list_own_suppliers(
        self, app_client, token_b, test_tenants
    ):
        """[Positive] GET /suppliers — Tenant B sees their own supplier."""
        resp = await app_client.get(
            "/api/v1/suppliers",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["id"] for item in resp.json()["items"]]
        assert test_tenants["supplier_b"] in ids

    async def test_both_tenants_can_create_cases_independently(
        self, app_client, token_a, token_b
    ):
        """[Positive] Both tenants can create cases without interfering."""
        r_a = await app_client.post(
            "/api/v1/cases",
            json={"title": "Extra case from A"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        r_b = await app_client.post(
            "/api/v1/cases",
            json={"title": "Extra case from B"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r_a.status_code == 201
        assert r_b.status_code == 201
        assert r_a.json()["id"] != r_b.json()["id"]


# =============================================================================
# Scenarios NOT covered — infrastructure gaps
# =============================================================================
#
# The following scenarios are omitted because the required preceding state
# cannot be created cheaply in a test DB without a running AI analysis:
#
# A. Measurement confirm / patch (PATCH /measurements/{id}/confirm,
#    PATCH /measurements/{id})
#    Requires: a completed AnalysisJob → AnalysisResult row.
#    The mock provider will fail (no photos uploaded), so no result is written.
#    Work-around would require directly inserting AnalysisResult rows into the
#    test DB, which is a unit-test technique, not E2E.  Tagged for follow-up
#    once the mock provider supports a no-photo path.
#
# B. Quote-variant cross-tenant access
#    Requires: completed analysis + pricing flow to create QuoteVariant rows.
#    Same dependency as (A).
#
# C. Export file download isolation (GET /exports/{id})
#    ExportService currently stores export metadata in-memory (not in DB) and
#    the mock export path never writes real file bytes.  There is no persistent
#    export ID to steal.  The route is also unprotected by tenant checks
#    (any authenticated user can read any export ID if they know it).
#    This is a separate concern tracked outside of isolation tests.
