from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.repositories.project_repository import ProjectRepository
from app.services.analysis_service import AnalysisJobCreateResult, AnalysisService
from app.services.quote_variant_service import QuoteVariantService


class CaseCommand(str, Enum):
    REQUEST_QUOTE_RECALCULATION = "request_quote_recalculation"


@dataclass(frozen=True)
class RequestQuoteRecalculationCommand:
    case_id: str
    organization_id: str | None
    requested_by_user_id: str | None
    is_superadmin_context: bool
    parent_job_id: str | None = None


@dataclass(frozen=True)
class CreateQuoteRecalcRecord:
    parent_job_id: str | None = None


@dataclass(frozen=True)
class EnqueueQuoteRecalcTransport:
    dispatch: str = "quote.enqueue"


@dataclass(frozen=True)
class EmitEventSpec:
    event_type: str


@dataclass(frozen=True)
class Rule:
    next_state: str
    before_commit: tuple[CreateQuoteRecalcRecord, ...]
    after_commit: tuple[EnqueueQuoteRecalcTransport, ...]
    events: tuple[EmitEventSpec, ...]


@dataclass(frozen=True)
class CommandResult:
    next_state: str
    before_commit_records: tuple[CreateQuoteRecalcRecord, ...]
    after_commit_jobs: tuple[EnqueueQuoteRecalcTransport, ...]
    emitted_events: tuple[EmitEventSpec, ...]


class QuoteRecalculationCommandError(ValueError):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


# Current runtime still uses legacy statuses. The command path is already
# table-driven and fail-closed, while the full proposal_pending migration
# remains a separate orchestration step.
RULES: dict[tuple[str, CaseCommand], Rule] = {
    (
        "proposal_ready",
        CaseCommand.REQUEST_QUOTE_RECALCULATION,
    ): Rule(
        next_state="proposal_ready",
        before_commit=(CreateQuoteRecalcRecord(),),
        after_commit=(EnqueueQuoteRecalcTransport(),),
        events=(EmitEventSpec("quote_recalculation_requested"),),
    ),
    (
        "quote_ready",
        CaseCommand.REQUEST_QUOTE_RECALCULATION,
    ): Rule(
        next_state="quote_ready",
        before_commit=(CreateQuoteRecalcRecord(),),
        after_commit=(EnqueueQuoteRecalcTransport(),),
        events=(EmitEventSpec("quote_recalculation_requested"),),
    ),
}


def handle_command(state: str, command: CaseCommand) -> CommandResult:
    rule = RULES.get((state, command))
    if rule is None:
        allowed = sorted(
            cmd.value for current_state, cmd in RULES.keys() if current_state == state
        )
        raise QuoteRecalculationCommandError(
            f"Command '{command.value}' is not allowed from state '{state}'. "
            f"Allowed commands: {allowed or 'none'}.",
        )

    return CommandResult(
        next_state=rule.next_state,
        before_commit_records=rule.before_commit,
        after_commit_jobs=rule.after_commit,
        emitted_events=rule.events,
    )


class QuoteRecalculationCommandService:
    """Table-driven command entry point for manual quote recalculation."""

    def __init__(
        self,
        project_repository: ProjectRepository,
        quote_variant_service: QuoteVariantService,
        analysis_service: AnalysisService,
        *,
        job_queue,
    ) -> None:
        self.project_repository = project_repository
        self.quote_variant_service = quote_variant_service
        self.analysis_service = analysis_service
        self.job_queue = job_queue

    async def handle(
        self,
        command: RequestQuoteRecalculationCommand,
    ) -> AnalysisJobCreateResult | None:
        project = await self.project_repository.get_project_lean(
            command.case_id,
            organization_id=command.organization_id,
        )
        if project is None:
            return None

        result = handle_command(
            project.status,
            CaseCommand.REQUEST_QUOTE_RECALCULATION,
        )

        can_recalculate = await self.quote_variant_service.can_recalculate_quote_variants(
            command.case_id
        )
        if not can_recalculate:
            raise QuoteRecalculationCommandError(
                "Estimates cannot be recalculated without an analysis result.",
                status_code=400,
            )

        create_result = await self.analysis_service.create_quote_recalculation_job_record(
            project_id=command.case_id,
            organization_id=command.organization_id,
            requested_by_user_id=command.requested_by_user_id,
            parent_job_id=command.parent_job_id,
        )
        if not create_result.created_new:
            return create_result

        if result.after_commit_jobs:
            return await self.analysis_service.enqueue_existing_job_transport(
                create_result.job,
                project_id=command.case_id,
                organization_id=command.organization_id,
                job_queue=self.job_queue,
                is_superadmin_context=command.is_superadmin_context,
            )
        return create_result
