"""Offer processing domain constants and state machine rules.

State machine:
    submitted   → queued      (automatic on POST /offer-requests)
    queued      → processing  (worker picks up job)
    processing  → needs_more_info  (AI returned INSUFFICIENT_DATA)
    processing  → needs_review     (AI completed, awaiting human approval)
    processing  → failed           (retries exhausted)
    needs_more_info → queued       (client POSTed /more-info)
    needs_review    → completed    (operator approved OR auto_review_bypass=True)
    completed   → [sent]           (auto_send=True triggers send, else manual)
    any non-terminal → cancelled   (explicit POST /cancel)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Status values
# ---------------------------------------------------------------------------

OFFER_STATUS_SUBMITTED       = "submitted"
OFFER_STATUS_QUEUED          = "queued"
OFFER_STATUS_PROCESSING      = "processing"
OFFER_STATUS_NEEDS_MORE_INFO = "needs_more_info"
OFFER_STATUS_NEEDS_REVIEW    = "needs_review"
OFFER_STATUS_COMPLETED       = "completed"
OFFER_STATUS_FAILED          = "failed"
OFFER_STATUS_CANCELLED       = "cancelled"

OFFER_TERMINAL_STATUSES: frozenset[str] = frozenset({
    OFFER_STATUS_COMPLETED,
    OFFER_STATUS_FAILED,
    OFFER_STATUS_CANCELLED,
})

OFFER_LOCKED_STATUSES: frozenset[str] = frozenset({
    OFFER_STATUS_PROCESSING,
    OFFER_STATUS_NEEDS_REVIEW,
    OFFER_STATUS_COMPLETED,
})

# ---------------------------------------------------------------------------
# Job status values
# ---------------------------------------------------------------------------

JOB_STATUS_QUEUED     = "queued"
JOB_STATUS_RUNNING    = "running"
JOB_STATUS_COMPLETED  = "completed"
JOB_STATUS_FAILED     = "failed"
JOB_STATUS_CANCELLED  = "cancelled"

# ---------------------------------------------------------------------------
# Agent run outcomes
# ---------------------------------------------------------------------------

AGENT_OUTCOME_OFFER_GENERATED  = "offer_generated"
AGENT_OUTCOME_INSUFFICIENT_DATA = "insufficient_data"
AGENT_OUTCOME_ERROR            = "error"
AGENT_OUTCOME_CANCELLED        = "cancelled"

# ---------------------------------------------------------------------------
# Error codes (stored in offer_jobs.last_error_code)
# ---------------------------------------------------------------------------

ERROR_PROVIDER_TIMEOUT        = "PROVIDER_TIMEOUT"
ERROR_PROVIDER_RATE_LIMITED   = "PROVIDER_RATE_LIMITED"
ERROR_PROVIDER_UNAVAILABLE    = "PROVIDER_UNAVAILABLE"
ERROR_VALIDATION_FAILED       = "VALIDATION_FAILED"
ERROR_SNAPSHOT_BUILD_FAILED   = "SNAPSHOT_BUILD_FAILED"
ERROR_BUDGET_EXHAUSTED        = "BUDGET_EXHAUSTED"
ERROR_UNKNOWN                 = "UNKNOWN"

# Retryable errors — worker will retry with backoff
RETRYABLE_ERROR_CODES: frozenset[str] = frozenset({
    ERROR_PROVIDER_TIMEOUT,
    ERROR_PROVIDER_RATE_LIMITED,
    ERROR_PROVIDER_UNAVAILABLE,
})

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Retry backoff schedule (seconds)
# ---------------------------------------------------------------------------

RETRY_BACKOFF_SECONDS: tuple[int, ...] = (30, 120, 600)  # attempt 1, 2, 3

# ---------------------------------------------------------------------------
# Poison job detection threshold
# ---------------------------------------------------------------------------

# After this many consecutive failures with the SAME error_code, the job is
# moved directly to failed regardless of remaining retries.
# Prevents exponential retry storms from structurally broken inputs (malformed
# parameters, unsupported image formats, invalid work_type_code) that will
# never succeed on any retry.
POISON_THRESHOLD: int = 3

# ---------------------------------------------------------------------------
# Allowed status transitions
# ---------------------------------------------------------------------------

_OFFER_TRANSITIONS: dict[str, frozenset[str]] = {
    OFFER_STATUS_SUBMITTED:       frozenset({OFFER_STATUS_QUEUED, OFFER_STATUS_CANCELLED}),
    OFFER_STATUS_QUEUED:          frozenset({OFFER_STATUS_PROCESSING, OFFER_STATUS_CANCELLED}),
    OFFER_STATUS_PROCESSING:      frozenset({OFFER_STATUS_NEEDS_MORE_INFO, OFFER_STATUS_NEEDS_REVIEW, OFFER_STATUS_FAILED, OFFER_STATUS_CANCELLED}),
    OFFER_STATUS_NEEDS_MORE_INFO: frozenset({OFFER_STATUS_QUEUED, OFFER_STATUS_CANCELLED}),
    OFFER_STATUS_NEEDS_REVIEW:    frozenset({OFFER_STATUS_COMPLETED, OFFER_STATUS_CANCELLED}),
    OFFER_STATUS_COMPLETED:       frozenset(),
    OFFER_STATUS_FAILED:          frozenset(),
    OFFER_STATUS_CANCELLED:       frozenset(),
}


def is_valid_offer_transition(from_status: str, to_status: str) -> bool:
    return to_status in _OFFER_TRANSITIONS.get(from_status, frozenset())


class InvalidOfferTransitionError(ValueError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(f"Cannot transition offer from '{from_status}' to '{to_status}'.")
        self.from_status = from_status
        self.to_status = to_status


def require_offer_transition(from_status: str, to_status: str) -> None:
    if not is_valid_offer_transition(from_status, to_status):
        raise InvalidOfferTransitionError(from_status, to_status)
