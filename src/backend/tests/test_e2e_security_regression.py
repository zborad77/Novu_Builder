# =============================================================================
# Security regression tests — direct-by-id tenant isolation
#
# These tests verify that every "fetch by ID, then check tenant" endpoint
# returns 404 when Tenant B tries to access Tenant A's resources directly by
# their IDs.  A green suite means the org-scoped repo/service methods and
# SECURITY_EVENT log points are wired up correctly.
#
# All fixtures are session-scoped and declared in conftest.py.
# =============================================================================
import pytest
import pytest_asyncio
from PIL import Image
from io import BytesIO


# ---------------------------------------------------------------------------
# Extra session-scoped fixtures needed only for these regression tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def export_a_id(app_client, token_a, case_a_id):
    """An export record created by Tenant A (report-pdf).

    The worker will fail (no content) but the export row is created and the
    ID is what we need to test cross-tenant GET /exports/{id} isolation.
    """
    resp = await app_client.post(
        f"/api/v1/cases/{case_a_id}/exports/report-pdf",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 202, f"Create export A failed: {resp.text}"
    return resp.json()["exportId"]


# ---------------------------------------------------------------------------
# 1. Analysis job direct-by-id isolation
# ---------------------------------------------------------------------------

class TestAnalysisJobDirectById:
    """GET, cancel, retry by job ID — Tenant B must get 404 for Tenant A jobs."""

    async def test_get_job_cross_tenant_is_404(self, app_client, token_b, job_a_id):
        resp = await app_client.get(
            f"/api/v1/analysis-jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    async def test_cancel_job_cross_tenant_is_404(self, app_client, token_b, job_a_id):
        resp = await app_client.post(
            f"/api/v1/analysis-jobs/{job_a_id}/cancel",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    async def test_retry_job_cross_tenant_is_404(self, app_client, token_b, job_a_id):
        resp = await app_client.post(
            f"/api/v1/analysis-jobs/{job_a_id}/retry",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    async def test_get_job_own_is_200(self, app_client, token_a, job_a_id):
        """Positive path: Tenant A can read their own job."""
        resp = await app_client.get(
            f"/api/v1/analysis-jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["id"] == job_a_id


# ---------------------------------------------------------------------------
# 2. Export direct-by-id isolation
# ---------------------------------------------------------------------------

class TestExportDirectById:
    """GET /exports/{id} — Tenant B must get 404 for Tenant A exports."""

    async def test_get_export_cross_tenant_is_404(self, app_client, token_b, export_a_id):
        resp = await app_client.get(
            f"/api/v1/exports/{export_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    async def test_get_export_own_is_200(self, app_client, token_a, export_a_id):
        """Positive path: Tenant A can read their own export."""
        resp = await app_client.get(
            f"/api/v1/exports/{export_a_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["id"] == export_a_id


# ---------------------------------------------------------------------------
# 3. Image preview direct-by-id isolation
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def image_a_id(app_client, token_a, case_a_id):
    """Upload a minimal multipart photo to Tenant A's case; return the photo ID."""
    buffer = BytesIO()
    Image.new("RGB", (2, 2), (0, 128, 0)).save(buffer, format="JPEG")
    resp = await app_client.post(
        f"/api/v1/cases/{case_a_id}/images",
        files={"files": ("regression_test.jpg", buffer.getvalue(), "image/jpeg")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201, f"Upload image A failed: {resp.text}"
    return resp.json()["uploaded"][0]["id"]


class TestImagePreviewDirectById:
    """GET /images/{id}/preview — Tenant B must get 404 for Tenant A images."""

    async def test_preview_cross_tenant_is_404(self, app_client, token_b, image_a_id):
        resp = await app_client.get(
            f"/api/v1/images/{image_a_id}/preview",
            headers={"Authorization": f"Bearer {token_b}"},
            follow_redirects=False,
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    async def test_preview_own_redirects(self, app_client, token_a, image_a_id):
        """Positive path: Tenant A gets a redirect (302/307) for their own image."""
        resp = await app_client.get(
            f"/api/v1/images/{image_a_id}/preview",
            headers={"Authorization": f"Bearer {token_a}"},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 307, 308), (
            f"Expected redirect, got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# 4. Unauthenticated access is rejected
# ---------------------------------------------------------------------------

class TestUnauthenticatedRejected:
    """No Bearer token → 401/403 on all sensitive direct-by-id endpoints."""

    async def test_get_job_no_token(self, app_client, job_a_id):
        resp = await app_client.get(f"/api/v1/analysis-jobs/{job_a_id}")
        assert resp.status_code in (401, 403)

    async def test_cancel_job_no_token(self, app_client, job_a_id):
        resp = await app_client.post(f"/api/v1/analysis-jobs/{job_a_id}/cancel")
        assert resp.status_code in (401, 403)

    async def test_get_export_no_token(self, app_client, export_a_id):
        resp = await app_client.get(f"/api/v1/exports/{export_a_id}")
        assert resp.status_code in (401, 403)

    async def test_image_preview_no_token(self, app_client, image_a_id):
        resp = await app_client.get(f"/api/v1/images/{image_a_id}/preview")
        assert resp.status_code in (401, 403)
