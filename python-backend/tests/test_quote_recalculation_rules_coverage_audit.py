import pytest

from app.case_orchestration.orchestration_dispatch_registry import DISPATCH_REGISTRY
from app.case_orchestration.quote_recalculation import (
    CaseCommand,
    CreateQuoteRecalcRecord,
    EnqueueQuoteRecalcTransport,
    EmitEventSpec,
    QuoteRecalculationCommandError,
    RULES,
    Rule,
    handle_command,
)


EXPECTED_ALLOWED_RULE_KEYS = {
    ("proposal_ready", CaseCommand.REQUEST_QUOTE_RECALCULATION),
    ("quote_ready", CaseCommand.REQUEST_QUOTE_RECALCULATION),
}

KNOWN_CASE_STATES = {
    "draft",
    "intake",
    "analyzing",
    "proposal_pending",
    "proposal_ready",
    "proposal_approved",
    "quote_ready",
    "sent",
    "archived",
}


def test_quote_recalculation_rules_keys_match_expected_matrix() -> None:
    assert set(RULES.keys()) == EXPECTED_ALLOWED_RULE_KEYS


def test_quote_recalculation_rules_are_structurally_complete() -> None:
    for key, rule in RULES.items():
        assert isinstance(rule, Rule), key
        assert isinstance(rule.before_commit, tuple), key
        assert isinstance(rule.after_commit, tuple), key
        assert isinstance(rule.events, tuple), key
        assert len(rule.before_commit) == 1, key
        assert len(rule.after_commit) == 1, key
        assert len(rule.events) == 1, key
        assert isinstance(rule.before_commit[0], CreateQuoteRecalcRecord), key
        assert isinstance(rule.after_commit[0], EnqueueQuoteRecalcTransport), key
        assert isinstance(rule.events[0], EmitEventSpec), key


def test_quote_recalculation_rules_define_canonical_effect_map() -> None:
    for state, command in EXPECTED_ALLOWED_RULE_KEYS:
        result = handle_command(state, command)

        assert result.next_state == state
        assert result.before_commit_records == (CreateQuoteRecalcRecord(),)
        assert result.after_commit_jobs == (EnqueueQuoteRecalcTransport(),)
        assert result.emitted_events == (EmitEventSpec("quote_recalculation_requested"),)
        assert result.after_commit_jobs[0].dispatch == "quote.enqueue"
        assert result.after_commit_jobs[0].dispatch in DISPATCH_REGISTRY


def test_quote_recalculation_forbidden_state_command_pairs_fail_closed() -> None:
    allowed_states = {state for state, _command in EXPECTED_ALLOWED_RULE_KEYS}

    for state in KNOWN_CASE_STATES - allowed_states:
        with pytest.raises(QuoteRecalculationCommandError):
            handle_command(state, CaseCommand.REQUEST_QUOTE_RECALCULATION)


def test_quote_recalculation_allowed_states_have_explicit_event_name() -> None:
    emitted_event_names = {
        rule.events[0].event_type
        for rule in RULES.values()
    }

    assert emitted_event_names == {"quote_recalculation_requested"}
