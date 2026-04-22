from datetime import UTC, datetime

from app.models import AnalysisResult, Project
from app.services.analysis_service import build_ai_work_type_suggestion, to_read_model
from app.services.project_service import _build_latest_analysis_dict


def _analysis_result(
    *,
    result_id: str,
    work_type_code: str | None,
    area_confidence: float | None,
    object_type: str | None = "roof",
    recommended_scope: str | None = "repair",
) -> AnalysisResult:
    return AnalysisResult(
        id=result_id,
        project_id="prj_ai_suggestion",
        resolved_work_type_code=work_type_code,
        area_confidence=area_confidence,
        object_type=object_type,
        recommended_scope=recommended_scope,
        final_area_source="ai",
        created_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
    )


def test_build_ai_work_type_suggestion_marks_high_confidence_match_usable():
    result = _analysis_result(
        result_id="analysis_match_high",
        work_type_code="roof-repair",
        area_confidence=0.82,
    )

    suggestion = build_ai_work_type_suggestion(result)

    assert suggestion.workTypeCode == "roof-repair"
    assert suggestion.confidence == 0.82
    assert suggestion.isUsable is True
    assert suggestion.sourceAnalysisId == "analysis_match_high"
    assert suggestion.reason is None
    assert suggestion.warnings == []

    read_model = to_read_model(result)
    assert read_model.aiWorkTypeSuggestion is not None
    assert read_model.aiWorkTypeSuggestion.workTypeCode == "roof-repair"
    assert read_model.aiWorkTypeSuggestion.isUsable is True


def test_build_ai_work_type_suggestion_marks_missing_match_not_usable():
    result = _analysis_result(
        result_id="analysis_no_match",
        work_type_code=None,
        area_confidence=0.91,
        object_type=None,
        recommended_scope=None,
    )

    suggestion = build_ai_work_type_suggestion(result)

    assert suggestion.workTypeCode is None
    assert suggestion.confidence == 0.91
    assert suggestion.isUsable is False
    assert suggestion.reason == "NO_MATCH"
    assert suggestion.warnings == []


def test_latest_analysis_includes_ai_work_type_suggestion_payload():
    latest_result = _analysis_result(
        result_id="analysis_match_low",
        work_type_code="roof-repair",
        area_confidence=0.34,
    )
    project = Project(
        id="prj_ai_suggestion",
        organization_id="org_ai_suggestion",
        created_by_user_id="usr_ai_suggestion",
        title="AI Suggestion Case",
        status="analyzing",
        created_at=datetime(2026, 4, 19, 9, 0, tzinfo=UTC),
    )
    project.analysis_results = [latest_result]

    latest_analysis = _build_latest_analysis_dict(project)

    assert latest_analysis is not None
    assert latest_analysis["workTypeCode"] == "roof-repair"
    assert latest_analysis["aiWorkTypeSuggestion"] == {
        "workTypeCode": "roof-repair",
        "confidence": 0.34,
        "isUsable": False,
        "objectType": "roof",
        "recommendedScope": "repair",
        "sourceAnalysisId": "analysis_match_low",
        "reason": None,
        "warnings": ["LOW_CONFIDENCE"],
    }
