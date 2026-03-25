"""
/admin/jobs sanitization, pagination and filtering tests.

Coverage:
1. _sanitize_admin_job — unit tests for field removal and truncation
2. Response sanitization — routes use sanitizer (source checks)
3. Pagination — limit default/max, offset parameter
4. Filtering — org_id, status (source checks)
5. Non-admin endpoint not affected
"""
import inspect

import pytest

from app.api.routes.admin import (
    _ADMIN_JOB_MAX_ERROR_LEN,
    _sanitize_admin_job,
    get_admin_job,
    list_all_jobs,
)
from app.services.analysis_service import to_job_read


# ── 1. _sanitize_admin_job unit tests ──────────────────────────────────────────

class TestSanitizeAdminJob:

    def _make_job_dict(self, **overrides) -> dict:
        base = {
            "id": "job-1",
            "projectId": "proj-1",
            "status": "failed",
            "jobType": "analysis",
            "requestedByUserId": "user-1",
            "parentJobId": None,
            "retryCount": 0,
            "startedAt": None,
            "finishedAt": None,
            "durationSeconds": None,
            "errorMessage": "Something went wrong",
            "errorTraceback": (
                'Traceback (most recent call last):\n'
                '  File "/app/services/analysis_service.py", line 42, in execute_job\n'
                '    raise ValueError("internal detail")\n'
                'ValueError: internal detail\n'
            ),
            "inputPayload": {"provider": "mock", "photo_count": 3},
            "outputSummary": None,
            "createdAt": None,
            "caseTitle": "Test Case",
            "orgId": "org-1",
            "orgName": "Test Org",
        }
        base.update(overrides)
        return base

    # -- errorTraceback removal --

    def test_sanitizer_removes_error_traceback(self):
        raw = self._make_job_dict()
        sanitized = _sanitize_admin_job(raw)
        assert "errorTraceback" not in sanitized

    def test_sanitizer_does_not_affect_other_fields(self):
        raw = self._make_job_dict()
        sanitized = _sanitize_admin_job(raw)
        for key in ("id", "projectId", "status", "errorMessage", "inputPayload", "orgId", "orgName"):
            assert key in sanitized, f"field '{key}' must be preserved"

    def test_sanitizer_with_no_traceback_field(self):
        """Sanitizer must handle dicts that never had errorTraceback."""
        raw = self._make_job_dict()
        del raw["errorTraceback"]
        sanitized = _sanitize_admin_job(raw)
        assert "errorTraceback" not in sanitized
        assert sanitized["status"] == "failed"

    def test_sanitizer_with_none_traceback(self):
        """None traceback must simply not appear in output."""
        raw = self._make_job_dict(errorTraceback=None)
        sanitized = _sanitize_admin_job(raw)
        assert "errorTraceback" not in sanitized

    # -- errorMessage truncation --

    def test_sanitizer_keeps_short_error_message(self):
        short_msg = "File not found"
        raw = self._make_job_dict(errorMessage=short_msg)
        sanitized = _sanitize_admin_job(raw)
        assert sanitized["errorMessage"] == short_msg

    def test_sanitizer_truncates_long_error_message(self):
        long_msg = "x" * (_ADMIN_JOB_MAX_ERROR_LEN + 100)
        raw = self._make_job_dict(errorMessage=long_msg)
        sanitized = _sanitize_admin_job(raw)
        msg = sanitized["errorMessage"]
        assert len(msg) <= _ADMIN_JOB_MAX_ERROR_LEN + 20  # allow for " … [truncated]" suffix
        assert "[truncated]" in msg
        assert msg.startswith("x" * _ADMIN_JOB_MAX_ERROR_LEN)

    def test_sanitizer_truncation_boundary(self):
        """Message of exactly max length must NOT be truncated."""
        exact_msg = "a" * _ADMIN_JOB_MAX_ERROR_LEN
        raw = self._make_job_dict(errorMessage=exact_msg)
        sanitized = _sanitize_admin_job(raw)
        assert sanitized["errorMessage"] == exact_msg
        assert "[truncated]" not in sanitized["errorMessage"]

    def test_sanitizer_keeps_none_error_message(self):
        raw = self._make_job_dict(errorMessage=None)
        sanitized = _sanitize_admin_job(raw)
        assert sanitized["errorMessage"] is None

    # -- sensitive fields never in output --

    def test_no_file_paths_in_traceback_field(self):
        """Verifies by-design: errorTraceback contains paths; sanitizer removes it."""
        raw = self._make_job_dict()
        assert "/app/services" in raw["errorTraceback"]  # confirms test data is realistic
        sanitized = _sanitize_admin_job(raw)
        assert "errorTraceback" not in sanitized

    def test_stack_trace_keywords_not_in_output(self):
        """After sanitization the output must not contain Python stack trace markers."""
        raw = self._make_job_dict()
        sanitized = _sanitize_admin_job(raw)
        output_str = str(sanitized)
        assert "Traceback (most recent call last)" not in output_str
        assert "File \"/app" not in output_str

    # -- operational fields preserved --

    def test_input_payload_preserved(self):
        payload = {"provider": "openai", "photo_count": 5}
        raw = self._make_job_dict(inputPayload=payload)
        assert _sanitize_admin_job(raw)["inputPayload"] == payload

    def test_output_summary_preserved(self):
        summary = {"model_name": "gpt-4o", "estimated_area_sqm": 12.5}
        raw = self._make_job_dict(outputSummary=summary)
        assert _sanitize_admin_job(raw)["outputSummary"] == summary

    def test_org_context_preserved(self):
        raw = self._make_job_dict(orgId="org-42", orgName="Acme")
        sanitized = _sanitize_admin_job(raw)
        assert sanitized["orgId"] == "org-42"
        assert sanitized["orgName"] == "Acme"


# ── 2. Routes use sanitizer ────────────────────────────────────────────────────

class TestRoutesSanitize:

    def test_list_all_jobs_calls_sanitize(self):
        src = inspect.getsource(list_all_jobs)
        assert "_sanitize_admin_job(" in src

    def test_get_admin_job_calls_sanitize(self):
        src = inspect.getsource(get_admin_job)
        assert "_sanitize_admin_job(" in src

    def test_sanitize_wraps_enrich(self):
        """Sanitizer must be applied around _enrich_job, not instead of it."""
        src = inspect.getsource(list_all_jobs)
        assert "_sanitize_admin_job(_enrich_job(" in src or (
            "_enrich_job(" in src and "_sanitize_admin_job(" in src
        )

    def test_max_error_len_constant_defined(self):
        """Constant controlling truncation must be explicitly defined."""
        assert isinstance(_ADMIN_JOB_MAX_ERROR_LEN, int)
        assert 100 <= _ADMIN_JOB_MAX_ERROR_LEN <= 2000  # sanity range


# ── 3. Pagination ──────────────────────────────────────────────────────────────

class TestAdminJobsPagination:

    def test_offset_param_exists(self):
        src = inspect.getsource(list_all_jobs)
        assert "offset" in src

    def test_offset_default_zero(self):
        src = inspect.getsource(list_all_jobs)
        assert "default=0" in src

    def test_offset_applied_to_query(self):
        src = inspect.getsource(list_all_jobs)
        assert ".offset(offset)" in src

    def test_limit_applied_to_query(self):
        src = inspect.getsource(list_all_jobs)
        assert ".limit(limit)" in src

    def test_limit_default_50(self):
        src = inspect.getsource(list_all_jobs)
        assert "default=50" in src

    def test_limit_hard_cap_200(self):
        src = inspect.getsource(list_all_jobs)
        assert "le=200" in src

    def test_limit_min_ge_1(self):
        src = inspect.getsource(list_all_jobs)
        assert "ge=1" in src

    def test_offset_non_negative(self):
        src = inspect.getsource(list_all_jobs)
        assert "ge=0" in src


# ── 4. Filtering ───────────────────────────────────────────────────────────────

class TestAdminJobsFiltering:

    def test_status_filter_applied(self):
        src = inspect.getsource(list_all_jobs)
        assert "AnalysisJob.status == job_status" in src

    def test_org_id_filter_applied(self):
        src = inspect.getsource(list_all_jobs)
        assert "Project.organization_id == org_id" in src

    def test_results_ordered_descending(self):
        src = inspect.getsource(list_all_jobs)
        assert "created_at.desc()" in src

    def test_status_param_aliased(self):
        """status query param uses alias='status' for clean URL."""
        src = inspect.getsource(list_all_jobs)
        assert 'alias="status"' in src or "alias='status'" in src


# ── 5. Non-admin endpoint not affected ────────────────────────────────────────

class TestNonAdminJobsUnchanged:

    def test_to_job_read_still_returns_traceback_for_non_admin(self):
        """to_job_read (used by non-admin routes) must not be altered.
        Sanitization is admin-only and lives in the admin route layer.
        """
        src = inspect.getsource(to_job_read)
        assert "errorTraceback" in src

    def test_sanitize_not_imported_in_analysis_service(self):
        """Sanitization helper must live in admin routes, not bleed into service layer."""
        from app.services import analysis_service
        assert not hasattr(analysis_service, "_sanitize_admin_job")
