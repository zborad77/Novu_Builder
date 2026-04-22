from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes.estimates import recalculate_case_estimates
from app.case_orchestration.quote_recalculation import QuoteRecalculationCommandError
from app.schemas.quote_variant import QuoteVariantRecalculateResponse
from app.services.analysis_service import AnalysisJobCreateResult


@pytest.mark.asyncio
async def test_recalculate_case_estimates_uses_command_service():
    current_user = MagicMock(id="usr-1", organizationId="org-1", isSuperAdmin=False)
    queued_job = MagicMock(
        id="job-quote-1",
        status="queued",
        job_type="quote_recalculation",
    )

    command_service = MagicMock(
        handle=AsyncMock(
            return_value=AnalysisJobCreateResult(job=queued_job, created_new=True)
        )
    )

    response = await recalculate_case_estimates(
        case_id="case-1",
        current_user=current_user,
        commands=command_service,
    )

    assert isinstance(response, QuoteVariantRecalculateResponse)
    assert response.variants == []
    assert response.jobId == "job-quote-1"
    assert response.jobStatus == "queued"
    assert response.jobType == "quote_recalculation"
    assert response.createdNew is True
    command_service.handle.assert_awaited_once()
    command = command_service.handle.await_args.args[0]
    assert command.case_id == "case-1"
    assert command.organization_id == "org-1"
    assert command.requested_by_user_id == "usr-1"
    assert command.parent_job_id is None
    assert command.is_superadmin_context is False


@pytest.mark.asyncio
async def test_recalculate_case_estimates_maps_command_error_to_http():
    current_user = MagicMock(id="usr-1", organizationId="org-1", isSuperAdmin=False)
    command_service = MagicMock(
        handle=AsyncMock(
            side_effect=QuoteRecalculationCommandError(
                "Quote recalculation is only allowed in statuses: proposal_ready, quote_ready. Current status is 'draft'."
            )
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await recalculate_case_estimates(
            case_id="case-1",
            current_user=current_user,
            commands=command_service,
        )

    assert exc_info.value.status_code == 409
    command_service.handle.assert_awaited_once()
