"""Use-case layer for Project status transitions.

Every status change in the system MUST go through one of the named action
methods in ``CaseActionService``.  Direct writes to ``Project.status`` outside
this module are a bug.

Human-triggered actions (all require an actor_user_id):
    submit              draft          → intake
    start_analysis      intake         → analyzing
    approve_proposal    proposal_ready → quote_ready
    send_quote          quote_ready    → sent          (guards: final proposal required)
    complete            sent           → archived
    return_to_draft     any valid      → draft
    cancel              any valid      → cancelled

Worker / system-triggered (actor_user_id=None):
    worker_proposal_ready   analyzing → proposal_ready
    worker_quote_ready       analyzing → quote_ready
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.case_workflow.effects import EffectContext, run_after_commit, run_before_commit
from app.case_workflow.transitions import (
    TransitionError,
    plan_transition,
    update_case_state,
)
from app.models import ProjectStatusHistory  # noqa: F401  (imported so ORM sees model)
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectDetail
from app.services.project_service import build_project_detail

# Importing action_effects registers all @before_commit / @after_commit decorators.
import app.case_workflow.action_effects  # noqa: F401

if TYPE_CHECKING:
    from app.models.domain import Project

logger = structlog.get_logger(__name__)


class CaseActionError(ValueError):
    """Business-rule violation during a case action (maps to HTTP 409)."""


class CaseActionService:
    def __init__(self, repository: ProjectRepository, *, work_queue=None) -> None:
        self.repository = repository
        self.work_queue = work_queue

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_for_transition(self, project_id: str, *, organization_id: str | None):
        """Lean fetch — only the Project row is needed for the transition."""
        return await self.repository.get_project_lean(project_id, organization_id=organization_id)

    async def _transition_and_return(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        to_status: str,
        action: str,
        actor_user_id: str | None,
        actor_role: str,
        reason: str | None,
        _preloaded_project: "Project | None" = None,
    ) -> ProjectDetail | None:
        """Apply transition → run before-commit effects → commit → run after-commit effects.

        *_preloaded_project* may be supplied by callers that have already fetched
        the full project graph (e.g. send_quote, which needs relationships for its
        guard check).  When omitted, a lean fetch is performed.
        """
        project = _preloaded_project or await self._load_for_transition(
            project_id, organization_id=organization_id
        )
        if project is None:
            return None
        from_status = project.status

        try:
            transition = plan_transition(
                project,
                to_status,
                actor_user_id=actor_user_id,
                reason=reason,
            )
            await update_case_state(project, transition, session=self.repository.session)
        except TransitionError as exc:
            raise CaseActionError(str(exc)) from exc

        ctx = EffectContext(
            project=project,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            organization_id=organization_id,
            is_superadmin_context=actor_role == "superadmin",
            session=self.repository.session,
            work_queue=self.work_queue,
        )
        await run_before_commit(ctx)
        await self.repository.session.commit()
        await run_after_commit(ctx)

        full = await self.repository.get_project(project_id, organization_id=organization_id)
        return build_project_detail(full, actor_role=actor_role)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Human-triggered actions
    # ------------------------------------------------------------------

    async def submit(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """draft → intake.  Customer / manager submits the case for processing."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="intake",
            action="submit",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def start_analysis(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """intake → analyzing.  Manager confirms photos are ready, kicks off analysis."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="analyzing",
            action="start_analysis",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def approve_proposal(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """proposal_ready → quote_ready.  Manager signs off on the AI proposal."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="quote_ready",
            action="approve_proposal",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def send_quote(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """quote_ready → sent.  Quote delivered to the client.

        Guard: a final proposal must exist before the case can be sent.
        The full project graph is pre-fetched for the guard check and reused
        by _transition_and_return to avoid a redundant query.
        """
        project = await self.repository.get_project(project_id, organization_id=organization_id)
        if project is None:
            return None

        if not getattr(project, "final_proposals", None):
            raise CaseActionError(
                "Final proposal must exist before the case can be sent."
            )

        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="sent",
            action="send_quote",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
            _preloaded_project=project,
        )

    async def complete(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """sent → archived.  Work completed / accepted."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="archived",
            action="complete",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def return_to_draft(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """any valid → draft.  Unlock for edits / re-submission."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="draft",
            action="return_to_draft",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    async def cancel(
        self,
        project_id: str,
        *,
        organization_id: str | None,
        actor_user_id: str,
        actor_role: str = "manager",
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """any valid → cancelled.  Explicitly abandon the case."""
        return await self._transition_and_return(
            project_id,
            organization_id=organization_id,
            to_status="cancelled",
            action="cancel",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Worker / system-triggered actions (actor_user_id=None)
    # ------------------------------------------------------------------

    async def worker_proposal_ready(
        self,
        project_id: str,
        *,
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """analyzing → proposal_ready.  Called by the AI pipeline worker."""
        return await self._transition_and_return(
            project_id,
            organization_id=None,
            to_status="proposal_ready",
            action="worker_proposal_ready",
            actor_user_id=None,
            actor_role="manager",
            reason=reason,
        )

    async def worker_quote_ready(
        self,
        project_id: str,
        *,
        reason: str | None = None,
    ) -> ProjectDetail | None:
        """analyzing → quote_ready.  Worker fast-path: skips proposal step."""
        return await self._transition_and_return(
            project_id,
            organization_id=None,
            to_status="quote_ready",
            action="worker_quote_ready",
            actor_user_id=None,
            actor_role="manager",
            reason=reason,
        )
