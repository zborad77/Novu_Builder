import pytest

from app.case_orchestration.quote_recalculation import (
    CaseCommand,
    CreateQuoteRecalcRecord,
    EnqueueQuoteRecalcTransport,
    EmitEventSpec,
    QuoteRecalculationCommandError,
    RULES,
    handle_command,
)


def test_request_quote_recalculation_is_rule_driven_for_proposal_ready() -> None:
    result = handle_command("proposal_ready", CaseCommand.REQUEST_QUOTE_RECALCULATION)

    assert result.next_state == "proposal_ready"
    assert result.before_commit_records == (CreateQuoteRecalcRecord(),)
    assert result.after_commit_jobs == (EnqueueQuoteRecalcTransport(),)
    assert result.emitted_events == (EmitEventSpec("quote_recalculation_requested"),)


def test_request_quote_recalculation_rejects_invalid_state_fail_closed() -> None:
    with pytest.raises(QuoteRecalculationCommandError):
        handle_command("draft", CaseCommand.REQUEST_QUOTE_RECALCULATION)


def test_quote_recalculation_rules_are_the_single_source_for_supported_states() -> None:
    supported_states = {
        state for state, command in RULES.keys() if command == CaseCommand.REQUEST_QUOTE_RECALCULATION
    }

    assert supported_states == {"proposal_ready", "quote_ready"}
