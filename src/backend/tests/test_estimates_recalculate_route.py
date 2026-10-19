from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes.estimates import recalculate_case_estimates
from app.schemas.quote_variant import QuoteVariantRecalculateResponse
from app.services.analysis_service import AnalysisJobCreateResult


@pytest.mark.asyncio
async def test_recalculate_case_estimates_enqueues_explicit_quote_job():
    current_user = MagicMock(id="usr-1", organizationId="org-1", isSuperAdmin=False)
    project = MagicMock(id="case-1")
    job_queue = AsyncMock()
    queued_job = MagicMock(
        id="job-quote-1",
        status="queued",
        job_type="quote_recalculation",
    )

    project_service = MagicMock(get_project=AsyncMock(return_value=project))
    quote_service = MagicMock(can_recalculate_quote_variants=AsyncMock(return_value=True))
    analysis_service = MagicMock(
        enqueue_quote_recalculation_job=AsyncMock(
            return_value=AnalysisJobCreateResult(job=queued_job, created_new=True)
        )
    )

    response = await recalculate_case_estimates(
        case_id="case-1",
        current_user=current_user,
        project_service=project_service,
        quote_service=quote_service,
        analysis_service=analysis_service,
        job_queue=job_queue,
    )

    assert isinstance(response, QuoteVariantRecalculateResponse)
    assert response.variants == []
    assert response.jobId == "job-quote-1"
    assert response.jobStatus == "queued"
    assert response.jobType == "quote_recalculation"
    assert response.createdNew is True
    analysis_service.enqueue_quote_recalculation_job.assert_awaited_once_with(
        project_id="case-1",
        organization_id="org-1",
        requested_by_user_id="usr-1",
        parent_job_id=None,
        job_queue=job_queue,
        is_superadmin_context=False,
    )


@pytest.mark.asyncio
async def test_recalculate_case_estimates_rejects_missing_analysis_prerequisite():
    current_user = MagicMock(id="usr-1", organizationId="org-1", isSuperAdmin=False)
    project = MagicMock(id="case-1")
    project_service = MagicMock(get_project=AsyncMock(return_value=project))
    quote_service = MagicMock(can_recalculate_quote_variants=AsyncMock(return_value=False))
    analysis_service = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await recalculate_case_estimates(
            case_id="case-1",
            current_user=current_user,
            project_service=project_service,
            quote_service=quote_service,
            analysis_service=analysis_service,
            job_queue=AsyncMock(),
        )

    assert exc_info.value.status_code == 400
    analysis_service.enqueue_quote_recalculation_job.assert_not_called()
