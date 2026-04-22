from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.project_service import assert_no_impossible_state


def _make_project(
    *,
    status: str,
    quote_variants=None,
    final_proposals=None,
    exports=None,
    analysis_jobs=None,
    analysis_results=None,
    status_history=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="prj_invariant_1",
        status=status,
        quote_variants=quote_variants,
        final_proposals=final_proposals,
        exports=exports,
        analysis_jobs=analysis_jobs,
        analysis_results=analysis_results,
        status_history=status_history,
    )


def test_proposal_ready_requires_quote_snapshot() -> None:
    project = _make_project(status="proposal_ready", quote_variants=[])

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "proposal_ready" in str(exc_info.value)


def test_proposal_ready_with_quote_snapshot_is_valid() -> None:
    project = _make_project(
        status="proposal_ready",
        quote_variants=[SimpleNamespace(id="qv_1", created_at=datetime.now(UTC))],
    )

    assert_no_impossible_state(project)


def test_other_statuses_do_not_require_quote_snapshot() -> None:
    project = _make_project(status="draft", quote_variants=[])

    assert_no_impossible_state(project)


def test_proposal_ready_rejects_stale_quote_snapshot_after_newer_analysis() -> None:
    now = datetime.now(UTC)
    project = _make_project(
        status="proposal_ready",
        quote_variants=[SimpleNamespace(id="qv_1", created_at=now)],
        analysis_results=[SimpleNamespace(id="ar_1", created_at=now + timedelta(minutes=1))],
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "latest quote snapshot" in str(exc_info.value)


def test_quote_ready_requires_final_proposal() -> None:
    project = _make_project(status="quote_ready", final_proposals=[])

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "quote_ready" in str(exc_info.value)


def test_sent_requires_final_proposal_and_export_record() -> None:
    project = _make_project(
        status="sent",
        final_proposals=[SimpleNamespace(id="fin_1")],
        exports=[],
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "sent" in str(exc_info.value)


def test_sent_with_final_proposal_and_export_record_is_valid() -> None:
    project = _make_project(
        status="sent",
        final_proposals=[SimpleNamespace(id="fin_1")],
        exports=[SimpleNamespace(id="exp_1", status="pending")],
        status_history=[
            SimpleNamespace(
                id="psh_1",
                to_status="quote_ready",
                transitioned_at=datetime.now(UTC),
                reason=None,
            )
        ],
    )

    assert_no_impossible_state(project)


def test_sent_requires_prior_quote_ready_transition() -> None:
    project = _make_project(
        status="sent",
        final_proposals=[SimpleNamespace(id="fin_1")],
        exports=[SimpleNamespace(id="exp_1", status="completed")],
        status_history=[],
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "TEMP invariant" in str(exc_info.value)
    assert "quote_ready" in str(exc_info.value)
    assert "proposal_approved" in str(exc_info.value)


def test_sent_temporary_invariant_still_rejects_proposal_approved_without_quote_ready() -> None:
    project = _make_project(
        status="sent",
        final_proposals=[SimpleNamespace(id="fin_1")],
        exports=[SimpleNamespace(id="exp_1", status="completed")],
        status_history=[
            SimpleNamespace(
                id="psh_1",
                to_status="proposal_approved",
                transitioned_at=datetime.now(UTC),
                reason=None,
            )
        ],
    )

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "TEMP invariant" in str(exc_info.value)
    assert "quote_ready" in str(exc_info.value)
    assert "proposal_approved_present=True" in str(exc_info.value)


def test_analyzing_requires_active_analysis_job() -> None:
    project = _make_project(status="analyzing", analysis_jobs=[])

    with pytest.raises(AssertionError) as exc_info:
        assert_no_impossible_state(project)

    assert "analyzing" in str(exc_info.value)


def test_analyzing_with_active_analysis_job_is_valid() -> None:
    project = _make_project(
        status="analyzing",
        analysis_jobs=[SimpleNamespace(id="job_1", status="running", job_type="manual_trigger")],
    )

    assert_no_impossible_state(project)


def test_analyzing_allows_explicit_reconciliation_marker_without_active_job() -> None:
    project = _make_project(
        status="analyzing",
        analysis_jobs=[],
        status_history=[
            SimpleNamespace(
                id="psh_1",
                to_status="analyzing",
                transitioned_at=datetime.now(UTC),
                reason="Worker reconciliation retry pending after restart.",
            )
        ],
    )

    assert_no_impossible_state(project)
