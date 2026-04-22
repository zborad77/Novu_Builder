"""Case (Project) status state machine.

Allowed transitions
-------------------
draft          -> intake | cancelled
intake         -> analyzing | draft | cancelled
analyzing      -> proposal_ready | quote_ready | draft | cancelled
proposal_ready -> quote_ready | draft | cancelled
quote_ready    -> sent | draft | cancelled
sent           -> archived | draft | cancelled
archived       terminal
cancelled      terminal

Locked statuses - photo uploads and parameter edits are rejected:
    {analyzing, proposal_ready, quote_ready, sent}

Usage
-----
    from app.case_workflow.transitions import plan_transition, update_case_state

    async with session.begin():
        project = await session.get(Project, project_id)
        transition = plan_transition(
            project,
            to_status="intake",
            actor_user_id=current_user.id,
            reason="Customer submitted via mobile",
        )
        await update_case_state(project, transition, session=session)
        # session.flush() / commit handled by caller
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.domain import Project, ProjectStatusHistory


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"intake", "cancelled"}),
    "intake": frozenset({"analyzing", "draft", "cancelled"}),
    "analyzing": frozenset({"proposal_ready", "quote_ready", "draft", "cancelled"}),
    "proposal_ready": frozenset({"quote_ready", "draft", "cancelled"}),
    "quote_ready": frozenset({"sent", "draft", "cancelled"}),
    "sent": frozenset({"archived", "draft", "cancelled"}),
    "archived": frozenset(),
    "cancelled": frozenset(),
}

LOCKED_STATUSES: frozenset[str] = frozenset(
    {"analyzing", "proposal_ready", "quote_ready", "sent"}
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"archived", "cancelled"})

VALID_STATUSES: frozenset[str] = frozenset(ALLOWED_TRANSITIONS.keys())


@dataclass(frozen=True)
class TransitionMeta:
    action: str
    label: str
    to_status: str
    requires_reason: bool


@dataclass(frozen=True)
class TransitionPlan:
    """Pure transition decision captured before any ORM mutation happens."""

    project_id: str
    from_status: str
    to_status: str
    actor_user_id: str | None
    reason: str | None
    transitioned_at: datetime


_HUMAN_REGISTRY: dict[tuple[str, str], TransitionMeta] = {
    ("draft", "intake"): TransitionMeta("submit", "Submit for intake", "intake", False),
    ("draft", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
    ("intake", "analyzing"): TransitionMeta("start_analysis", "Start analysis", "analyzing", False),
    ("intake", "draft"): TransitionMeta("return_to_draft", "Return to draft", "draft", True),
    ("intake", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
    ("analyzing", "draft"): TransitionMeta("return_to_draft", "Return to draft", "draft", True),
    ("analyzing", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
    ("proposal_ready", "quote_ready"): TransitionMeta("approve_proposal", "Approve proposal", "quote_ready", False),
    ("proposal_ready", "draft"): TransitionMeta("return_to_draft", "Return to draft", "draft", True),
    ("proposal_ready", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
    ("quote_ready", "sent"): TransitionMeta("send_quote", "Send quote to client", "sent", False),
    ("quote_ready", "draft"): TransitionMeta("return_to_draft", "Return to draft", "draft", True),
    ("quote_ready", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
    ("sent", "archived"): TransitionMeta("complete", "Mark as completed", "archived", False),
    ("sent", "draft"): TransitionMeta("return_to_draft", "Return to draft", "draft", True),
    ("sent", "cancelled"): TransitionMeta("cancel", "Cancel case", "cancelled", True),
}

_ACTION_SORT: dict[str, int] = {
    "submit": 0,
    "start_analysis": 0,
    "approve_proposal": 0,
    "send_quote": 0,
    "complete": 0,
    "return_to_draft": 10,
    "cancel": 20,
}

_MANAGER_ROLES: frozenset[str] = frozenset({"manager", "superadmin"})


def get_available_transitions(project: "Project", actor_role: str) -> list[TransitionMeta]:
    """Return the transitions this actor can trigger from the project's current status."""
    if actor_role not in _MANAGER_ROLES:
        return []
    current = project.status
    result = [
        meta
        for to in ALLOWED_TRANSITIONS.get(current, frozenset())
        if (meta := _HUMAN_REGISTRY.get((current, to))) is not None
    ]
    return sorted(result, key=lambda m: (_ACTION_SORT.get(m.action, 99), m.action))


class TransitionError(ValueError):
    """Raised when a status transition is not permitted."""


class LockedCaseError(TransitionError):
    """Raised when a mutating operation is attempted on a locked case."""


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


def plan_transition(
    project: "Project",
    to_status: str,
    *,
    actor_user_id: str | None = None,
    reason: str | None = None,
    session: "AsyncSession | None" = None,
) -> TransitionPlan:
    """Validate and return a pure transition plan."""
    del session  # kept for backwards-compatible call signatures during refactor

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

    return TransitionPlan(
        project_id=project.id,
        from_status=project.status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reason=reason,
        transitioned_at=datetime.now(timezone.utc),
    )


def _assert_transition_target_matches_project(
    project: "Project",
    transition: TransitionPlan,
) -> None:
    if project.id != transition.project_id:
        raise TransitionError(
            f"Transition plan project mismatch: expected {transition.project_id!r}, "
            f"got {project.id!r}."
        )

    if project.status != transition.from_status:
        raise TransitionError(
            f"Project {project.id!r} changed status from {transition.from_status!r} "
            f"to {project.status!r} before the transition plan was applied."
        )


def _build_status_history_entry(transition: TransitionPlan) -> "ProjectStatusHistory":
    from app.models.domain import ProjectStatusHistory

    return ProjectStatusHistory(
        id=f"psh_{uuid4().hex[:10]}",
        project_id=transition.project_id,
        from_status=transition.from_status,
        to_status=transition.to_status,
        transitioned_by_user_id=transition.actor_user_id,
        reason=transition.reason,
        transitioned_at=transition.transitioned_at,
    )


async def update_case_state(
    project: "Project",
    transition: TransitionPlan,
    *,
    session: "AsyncSession",
) -> None:
    """Execution-pipeline step: persist the planned case state change."""
    _assert_transition_target_matches_project(project, transition)

    result = await session.execute(
        update(type(project))
        .where(
            type(project).id == transition.project_id,
            type(project).status == transition.from_status,
        )
        .values(
            status=transition.to_status,
            status_changed_at=transition.transitioned_at,
            status_changed_by_user_id=transition.actor_user_id,
            updated_at=func.now(),
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        await session.refresh(project)
        raise TransitionError(
            f"Project {project.id!r} could not be updated from "
            f"{transition.from_status!r} to {transition.to_status!r}."
        )

    session.add(_build_status_history_entry(transition))
    await session.flush()
    await session.refresh(project)


def apply_transition_plan(
    project: "Project",
    transition: TransitionPlan,
    *,
    session: "AsyncSession | None" = None,
) -> None:
    """Legacy in-memory helper kept only for non-DB unit tests."""
    _assert_transition_target_matches_project(project, transition)
    if session is not None:
        raise RuntimeError(
            "Runtime code must use async update_case_state(...) instead of "
            "apply_transition_plan(..., session=...)."
        )

    history_entry = _build_status_history_entry(transition)
    setattr(project, "status", transition.to_status)
    setattr(project, "status_changed_at", transition.transitioned_at)
    setattr(project, "status_changed_by_user_id", transition.actor_user_id)
    project.status_history.append(history_entry)


async def execute_transition(
    project: "Project",
    to_status: str,
    *,
    actor_user_id: str | None = None,
    reason: str | None = None,
    session: "AsyncSession",
) -> TransitionPlan:
    """Plan and persist a transition through the explicit execution pipeline."""
    transition = plan_transition(
        project,
        to_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    await update_case_state(project, transition, session=session)
    return transition


def apply_transition(
    project: "Project",
    to_status: str,
    *,
    actor_user_id: str | None = None,
    reason: str | None = None,
    session: "AsyncSession | None" = None,
) -> TransitionPlan:
    """Backward-compatible non-DB helper for tests only."""
    if session is not None:
        raise RuntimeError(
            "Runtime code must use async execute_transition(..., session=...) instead "
            "of apply_transition(..., session=...)."
        )
    transition = plan_transition(
        project,
        to_status,
        actor_user_id=actor_user_id,
        reason=reason,
    )
    apply_transition_plan(project, transition)
    return transition
