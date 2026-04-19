"""Case (Project) status state machine.

Allowed transitions
-------------------
draft          → intake | cancelled
intake         → analyzing | draft | cancelled
analyzing      → proposal_ready | quote_ready | draft | cancelled
proposal_ready → quote_ready | draft | cancelled
quote_ready    → sent | draft | cancelled
sent           → archived | draft | cancelled
archived       terminal
cancelled      terminal

Locked statuses — photo uploads and parameter edits are rejected:
    {analyzing, proposal_ready, quote_ready, sent}

Usage
-----
    from app.case_workflow.transitions import apply_transition

    async with session.begin():
        project = await session.get(Project, project_id)
        apply_transition(
            project,
            to_status="intake",
            actor_user_id=current_user.id,
            reason="Customer submitted via mobile",
            session=session,
        )
        # session.flush() / commit handled by caller
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from uuid import uuid4

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.domain import Project


# ---------------------------------------------------------------------------
# Transition map
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft":          frozenset({"intake", "cancelled"}),
    "intake":         frozenset({"analyzing", "draft", "cancelled"}),
    "analyzing":      frozenset({"proposal_ready", "quote_ready", "draft", "cancelled"}),
    "proposal_ready": frozenset({"quote_ready", "draft", "cancelled"}),
    "quote_ready":    frozenset({"sent", "draft", "cancelled"}),
    "sent":           frozenset({"archived", "draft", "cancelled"}),
    "archived":       frozenset(),
    "cancelled":      frozenset(),
}

LOCKED_STATUSES: frozenset[str] = frozenset(
    {"analyzing", "proposal_ready", "quote_ready", "sent"}
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"archived", "cancelled"})

VALID_STATUSES: frozenset[str] = frozenset(ALLOWED_TRANSITIONS.keys())


# ---------------------------------------------------------------------------
# TransitionMeta — describes a single human-triggerable action
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransitionMeta:
    action: str           # maps to CaseActionService method name and URL segment
    label: str            # human-readable label (English; UI translates)
    to_status: str        # target status after the action
    requires_reason: bool # whether the UI should prompt for a reason


# All human-triggered transitions.  Worker-only paths (analyzing → proposal_ready /
# quote_ready) are intentionally absent — they are never shown in the UI.
_HUMAN_REGISTRY: dict[tuple[str, str], TransitionMeta] = {
    ("draft",          "intake"):       TransitionMeta("submit",           "Submit for intake",     "intake",         False),
    ("draft",          "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
    ("intake",         "analyzing"):    TransitionMeta("start_analysis",   "Start analysis",        "analyzing",      False),
    ("intake",         "draft"):        TransitionMeta("return_to_draft",  "Return to draft",       "draft",          True),
    ("intake",         "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
    ("analyzing",      "draft"):        TransitionMeta("return_to_draft",  "Return to draft",       "draft",          True),
    ("analyzing",      "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
    ("proposal_ready", "quote_ready"):  TransitionMeta("approve_proposal", "Approve proposal",      "quote_ready",    False),
    ("proposal_ready", "draft"):        TransitionMeta("return_to_draft",  "Return to draft",       "draft",          True),
    ("proposal_ready", "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
    ("quote_ready",    "sent"):         TransitionMeta("send_quote",       "Send quote to client",  "sent",           False),
    ("quote_ready",    "draft"):        TransitionMeta("return_to_draft",  "Return to draft",       "draft",          True),
    ("quote_ready",    "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
    ("sent",           "archived"):     TransitionMeta("complete",         "Mark as completed",     "archived",       False),
    ("sent",           "draft"):        TransitionMeta("return_to_draft",  "Return to draft",       "draft",          True),
    ("sent",           "cancelled"):    TransitionMeta("cancel",           "Cancel case",           "cancelled",      True),
}

# Forward actions first, rollback second, cancel last.
_ACTION_SORT: dict[str, int] = {
    "submit": 0, "start_analysis": 0, "approve_proposal": 0,
    "send_quote": 0, "complete": 0,
    "return_to_draft": 10,
    "cancel": 20,
}

# Roles allowed to trigger human-facing transitions.
_MANAGER_ROLES: frozenset[str] = frozenset({"manager", "superadmin"})


def get_available_transitions(project: "Project", actor_role: str) -> list[TransitionMeta]:
    """Return the transitions this actor can trigger from the project's current status.

    Technicians and unknown roles receive an empty list.
    Worker-only transitions (analyzing → proposal_ready/quote_ready) are never included.
    """
    if actor_role not in _MANAGER_ROLES:
        return []
    current = project.status
    result = [
        meta
        for to in ALLOWED_TRANSITIONS.get(current, frozenset())
        if (meta := _HUMAN_REGISTRY.get((current, to))) is not None
    ]
    return sorted(result, key=lambda m: (_ACTION_SORT.get(m.action, 99), m.action))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TransitionError(ValueError):
    """Raised when a status transition is not permitted."""


class LockedCaseError(TransitionError):
    """Raised when a mutating operation is attempted on a locked case."""


# ---------------------------------------------------------------------------
# Guard helpers (pure functions, no DB access)
# ---------------------------------------------------------------------------

def is_locked(project: "Project") -> bool:
    """Return True when the project is in a locked status."""
    return project.status in LOCKED_STATUSES


def assert_unlocked(project: "Project") -> None:
    """Raise LockedCaseError if the project is currently locked."""
    if is_locked(project):
        raise LockedCaseError(
            f"Project {project.id!r} is locked in status {project.status!r}. "
            "Return to 'draft' before making changes."
        )


def can_transition(current_status: str, to_status: str) -> bool:
    """Return True when the transition is in the allowed map."""
    return to_status in ALLOWED_TRANSITIONS.get(current_status, frozenset())


# ---------------------------------------------------------------------------
# Core transition engine
# ---------------------------------------------------------------------------

def apply_transition(
    project: "Project",
    to_status: str,
    *,
    actor_user_id: str | None = None,
    reason: str | None = None,
    session: "AsyncSession | None" = None,
) -> None:
    """Validate and apply a status transition in-place.

    Mutates *project* fields and appends a ``ProjectStatusHistory`` row to the
    SQLAlchemy session (if provided).  The caller is responsible for committing.

    Args:
        project:        The ``Project`` ORM instance to transition.
        to_status:      Target status string.
        actor_user_id:  ID of the user initiating the transition (may be None for
                        system-initiated transitions such as worker callbacks).
        reason:         Optional human-readable note recorded in history.
        session:        Active ``AsyncSession``.  Pass ``None`` only in tests that
                        manage history insertion themselves.

    Raises:
        TransitionError: When the transition is not allowed by the state machine.
    """
    if to_status not in VALID_STATUSES:
        raise TransitionError(
            f"Unknown target status {to_status!r}. "
            f"Valid values: {sorted(VALID_STATUSES)}"
        )

    if not can_transition(project.status, to_status):
        allowed = sorted(ALLOWED_TRANSITIONS.get(project.status, frozenset()))
        raise TransitionError(
            f"Cannot transition project {project.id!r} "
            f"from {project.status!r} to {to_status!r}. "
            f"Allowed targets: {allowed}"
        )

    from app.models.domain import ProjectStatusHistory  # local import — avoids circular

    now = datetime.now(timezone.utc)
    from_status = project.status

    # Mutate the project
    project.status = to_status
    project.status_changed_at = now
    project.status_changed_by_user_id = actor_user_id

    # Append history row
    history_entry = ProjectStatusHistory(
        id=f"psh_{uuid4().hex[:10]}",
        project_id=project.id,
        from_status=from_status,
        to_status=to_status,
        transitioned_by_user_id=actor_user_id,
        reason=reason,
        transitioned_at=now,
    )

    if session is not None:
        session.add(history_entry)
    else:
        # Fallback: attach via the ORM relationship so it is persisted when
        # the session owning *project* flushes.
        project.status_history.append(history_entry)
