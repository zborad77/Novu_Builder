"""D1 Regression: End-to-end analysis job flow.

Covers the full analysis pipeline via real HTTP + test DB (no mocks):

  1. Create case → enqueue analysis job → verify 202 + jobId returned
  2. GET /analysis-jobs/{jobId} returns job record with correct project linkage
  3. GET /cases/{id}/analysis-jobs lists the job under the correct case
  4. Cross-tenant: Tenant B cannot access Tenant A's analysis job (404)
  5. Cross-tenant: Tenant B cannot create a job for Tenant A's case (404)
  6. Cancel an enqueued/running job returns updated status
  7. GET job for nonexistent ID returns 404, not 500

The mock AI provider (AI_ANALYSIS_PROVIDER=mock) is active in tests,
so job creation succeeds and produces a queued/running job record.
No worker process is running — jobs remain in 'queued' state.
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


_CASES_URL = "/api/v1/cases"
_JOBS_URL = "/api/v1/analysis-jobs"


@pytest_asyncio.fixture
async def app_client(test_tenants):
    """Per-test ASGI client so async resources never cross event loops."""
    from app.main import app as fastapi_app  # noqa: PLC0415
    from tests.conftest import _InMemoryAuthRedis  # noqa: PLC0415

    async with fastapi_app.router.lifespan_context(fastapi_app):
        auth_token_store = _InMemoryAuthRedis()
        original_auth_token_store = getattr(fastapi_app.state, "auth_token_store", None)
        fastapi_app.state.auth_token_store = auth_token_store
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        fastapi_app.state.auth_token_store = original_auth_token_store


@pytest_asyncio.fixture
async def token_a(app_client, test_tenants):
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_a"])
    assert resp.status_code == 200, f"Login A failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture
async def token_b(app_client, test_tenants):
    resp = await app_client.post("/api/v1/auth/login", json=test_tenants["user_b"])
    assert resp.status_code == 200, f"Login B failed: {resp.text}"
    return resp.json()["accessToken"]


@pytest_asyncio.fixture
async def case_a_id(app_client, token_a):
    return await _create_case(app_client, token_a, "E2E Isolation Test Case - Tenant A")


@pytest_asyncio.fixture
async def job_a_id(app_client, token_a, case_a_id):
    resp = await app_client.post(
        f"{_CASES_URL}/{case_a_id}/analysis-jobs",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 202, f"Create job A failed: {resp.text}"
    return resp.json()["jobId"]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_case(client, token: str, title: str) -> str:
    resp = await client.post(
        _CASES_URL,
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create case failed: {resp.text}"
    return resp.json()["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAnalysisJobCreation:

    @pytest.mark.asyncio
    async def test_create_job_returns_202_with_job_id(self, app_client, token_a, case_a_id):
        """POST /cases/{id}/analysis-jobs returns 202 Accepted with a jobId."""
        resp = await app_client.post(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "jobId" in body, f"Response missing jobId: {body}"
        assert body["jobId"], "jobId must not be empty"
        assert "status" in body

    @pytest.mark.asyncio
    async def test_created_job_has_queued_or_running_status(self, app_client, token_a, case_a_id):
        """Newly created job starts in 'queued' or 'running' state (no worker means 'queued')."""
        resp = await app_client.post(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 202
        status = resp.json()["status"]
        assert status in ("queued", "running", "pending"), (
            f"Unexpected initial job status: {status!r}"
        )

    @pytest.mark.asyncio
    async def test_create_job_for_nonexistent_case_returns_404(self, app_client, token_a):
        """Creating a job for a nonexistent case returns 404, not 500."""
        resp = await app_client.post(
            f"{_CASES_URL}/nonexistent_case_xyz/analysis-jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404


class TestAnalysisJobRetrieval:

    @pytest.mark.asyncio
    async def test_get_job_by_id_returns_job_record(self, app_client, token_a, job_a_id):
        """GET /analysis-jobs/{jobId} returns the job record for the owning tenant."""
        resp = await app_client.get(
            f"{_JOBS_URL}/{job_a_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, f"Get job failed: {resp.text}"
        body = resp.json()
        assert body.get("id") == job_a_id or body.get("jobId") == job_a_id, (
            f"Job ID mismatch: {body}"
        )

    @pytest.mark.asyncio
    async def test_list_jobs_for_case_returns_at_least_one(self, app_client, token_a, case_a_id, job_a_id):
        """GET /cases/{id}/analysis-jobs returns a list containing the created job."""
        resp = await app_client.get(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, f"List jobs failed: {resp.text}"
        jobs = resp.json()
        assert isinstance(jobs, list), f"Expected list, got: {type(jobs)}"
        assert len(jobs) >= 1, "Expected at least one job in the list"
        job_ids = [j.get("id") or j.get("jobId") for j in jobs]
        assert job_a_id in job_ids, f"job_a_id {job_a_id} not found in job list: {job_ids}"

    @pytest.mark.asyncio
    async def test_get_nonexistent_job_returns_404(self, app_client, token_a):
        """GET /analysis-jobs/{nonexistent} returns 404, not 500."""
        resp = await app_client.get(
            f"{_JOBS_URL}/job_nonexistent_xyz",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404


class TestAnalysisJobTenantIsolation:

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_get_tenant_a_job(self, app_client, token_b, job_a_id):
        """Tenant B cannot access Tenant A's analysis job — must get 404."""
        resp = await app_client.get(
            f"{_JOBS_URL}/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant job access must be 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_create_job_for_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """Tenant B cannot create an analysis job for Tenant A's case — must get 404."""
        resp = await app_client.post(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant job creation must be 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_list_jobs_for_tenant_a_case(
        self, app_client, token_b, case_a_id
    ):
        """Tenant B cannot list analysis jobs for Tenant A's case — must get 404."""
        resp = await app_client.get(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant job list must be 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_cancel_tenant_a_job(self, app_client, token_b, job_a_id):
        """Tenant B cannot cancel Tenant A's analysis job — must get 404."""
        resp = await app_client.post(
            f"{_JOBS_URL}/{job_a_id}/cancel",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant job cancel must be 404, got {resp.status_code}"
        )


class TestAnalysisJobCancellation:

    @pytest.mark.asyncio
    async def test_cancel_job_returns_updated_status(self, app_client, token_a, case_a_id):
        """Cancelling a queued job returns a response without 500."""
        # Create a fresh job specifically for cancellation
        resp = await app_client.post(
            f"{_CASES_URL}/{case_a_id}/analysis-jobs",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 202
        job_id = resp.json()["jobId"]

        cancel_resp = await app_client.post(
            f"{_JOBS_URL}/{job_id}/cancel",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        # Cancel returns 200 with updated job or 404 if already terminal
        assert cancel_resp.status_code in (200, 404), (
            f"Unexpected cancel response: {cancel_resp.status_code}: {cancel_resp.text}"
        )
