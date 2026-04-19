"""D1 Regression: Case status business rule constraints.

Covers status transition guards enforced by the service layer:

  1. POST /cases/{id}/send returns 409 when no final proposal exists
  2. POST /cases/{id}/archive transitions any case to 'archived'
  3. Archived case can still be read (not 404)
  4. POST /cases/{id}/final-proposal returns 409 when proposal draft is not ready
     (not enough photos)
  5. Cross-tenant: tenant B cannot archive/send tenant A's case

These tests use real HTTP + test DB — no mocks.
"""
import pytest


_CASES_URL = "/api/v1/cases"


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _create_fresh_case(client, token: str, title: str = "Status Constraint Test") -> str:
    resp = await client.post(
        _CASES_URL,
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, f"Create case failed: {resp.text}"
    return resp.json()["id"]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCaseStatusConstraints:

    @pytest.mark.asyncio
    async def test_send_without_final_proposal_returns_409(self, app_client, token_a):
        """Sending a case without a final proposal must be rejected with 409."""
        case_id = await _create_fresh_case(app_client, token_a, "Send Guard Test")

        resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/send",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 for send without final proposal, got {resp.status_code}: {resp.text}"
        )
        assert "Final proposal" in resp.json().get("detail", ""), (
            f"Expected descriptive error message, got: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_archive_from_draft_returns_409(self, app_client, token_a):
        """Archive is only valid from 'sent'. Archiving a fresh draft must return 409."""
        case_id = await _create_fresh_case(app_client, token_a, "Archive Guard Test")

        resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/archive",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 409, (
            f"Expected 409 for archive from draft, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_cancelled_case_is_readable(self, app_client, token_a):
        """A cancelled case can still be retrieved via GET — terminal states are not deleted."""
        case_id = await _create_fresh_case(app_client, token_a, "Cancelled Readable Test")

        cancel_resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/cancel",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert cancel_resp.status_code == 200, f"Cancel failed: {cancel_resp.text}"
        assert cancel_resp.json()["status"] == "cancelled"

        resp = await app_client.get(
            f"{_CASES_URL}/{case_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200, f"Cancelled case must still be readable, got {resp.status_code}"
        assert resp.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_final_proposal_rejected_without_enough_photos(self, app_client, token_a):
        """Creating a final proposal fails with 409 when the draft is not ready (no photos)."""
        case_id = await _create_fresh_case(app_client, token_a, "Final Proposal Guard Test")

        resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/final-proposal",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        # Expect 409 — service raises ValueError when draft is not ready
        assert resp.status_code == 409, (
            f"Expected 409 for final proposal without ready draft, got {resp.status_code}: {resp.text}"
        )

    @pytest.mark.asyncio
    async def test_send_nonexistent_case_returns_404(self, app_client, token_a):
        """Sending a nonexistent case returns 404, not 500."""
        resp = await app_client.post(
            f"{_CASES_URL}/nonexistent_case_id/send",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_nonexistent_case_returns_404(self, app_client, token_a):
        """Archiving a nonexistent case returns 404, not 500."""
        resp = await app_client.post(
            f"{_CASES_URL}/nonexistent_case_id/archive",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_tenant_cannot_send_case(self, app_client, token_a, token_b):
        """Tenant B cannot send Tenant A's case — gets 404 (tenant isolation)."""
        case_id = await _create_fresh_case(app_client, token_a, "Cross-Tenant Send Test")

        resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/send",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        # Tenant B sees a 404 (resource scoped to org), not a 409 or 200
        assert resp.status_code == 404, (
            f"Cross-tenant send must return 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_cross_tenant_cannot_archive_case(self, app_client, token_a, token_b):
        """Tenant B cannot archive Tenant A's case — gets 404 (tenant isolation)."""
        case_id = await _create_fresh_case(app_client, token_a, "Cross-Tenant Archive Test")

        resp = await app_client.post(
            f"{_CASES_URL}/{case_id}/archive",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404, (
            f"Cross-tenant archive must return 404, got {resp.status_code}"
        )

    @pytest.mark.asyncio
    async def test_case_initial_status_is_draft(self, app_client, token_a):
        """A freshly created case has status 'draft' (guards against wrong default)."""
        case_id = await _create_fresh_case(app_client, token_a, "Initial Status Test")

        resp = await app_client.get(
            f"{_CASES_URL}/{case_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        status = resp.json()["status"]
        assert status == "draft", f"Expected initial status 'draft', got '{status}'"
