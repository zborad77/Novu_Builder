"""Integration tests for the Vision analysis pipeline (Step 15).

Test strategy:
  - Stage contract integrity    — each stage result is immutable and well-formed
  - LegacyProviderAdapter       — flat dict → stage results decomposition
  - PipelineOrchestrator        — route selection (legacy vs staged), end-to-end
  - StagedVisionPipeline path   — synthetic staged provider
  - run_project_analysis()      — backward-compat check via mock provider
  - Safe defaults               — missing / None fields in provider output
  - to_legacy_dict()            — PipelineRunResult round-trip
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.ai.pipeline_contracts import (
    DetectionStageResult,
    ExtractionStageResult,
    PipelineRunResult,
    WorkCatalogMappingResult,
)
from app.ai.pipeline import (
    LegacyProviderAdapter,
    PipelineOrchestrator,
    StagedVisionPipeline,
    _decompose_legacy_output,
    _is_staged,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FULL_PROVIDER_OUTPUT = {
    "providerKey": "mock",
    "jobType": "vision_mock",
    "objectType": "roof",
    "surfaceCondition": "requires_attention",
    "recommendedScope": "local_repair",
    "estimatedQuantity": 85.5,
    "estimatedUnit": "m2",
    "estimatedAreaSqm": 85.5,
    "areaConfidence": 0.78,
    "maskPolygon": [{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.2}],
    "materials": [{"name": "Opravna smes", "unit": "kg", "quantity": 12.0, "unitPrice": 42.0, "totalPrice": 504.0}],
    "workflowSteps": [{"step": 1, "name": "Kontrola", "description": "...", "estimatedHours": 1}],
    "estimatedTotalDays": 2.5,
    "laborHoursTotal": 8.0,
    "catalogAttributes": {"roof_pitch_deg": {"value": 18, "confidence": 0.75}},
    "validationWarnings": [],
    "resolvedWorkTypeCode": "roof-repair",
    "analysisProfileCode": "standard-roof",
    "analysisProfileVersion": "1.2",
    "modelName": "mock-vision",
    "modelVersion": "0.3",
}


def _make_project() -> dict:
    return {"id": "proj-1", "description": "Strecha oprava", "address_label": "Praha 1"}


def _make_photos() -> list[dict]:
    return [
        {"id": "ph-1", "orientation": "landscape", "hasGps": True, "width": 1920, "height": 1080},
        {"id": "ph-2", "orientation": "portrait", "hasGps": False, "width": 720, "height": 1280},
    ]


# ---------------------------------------------------------------------------
# Stage contract tests
# ---------------------------------------------------------------------------

class TestDetectionStageResult:
    def test_is_frozen(self):
        result = DetectionStageResult(
            object_type="roof",
            surface_condition="good",
            mask_polygon=None,
            area_confidence=0.9,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.object_type = "facade"  # type: ignore[misc]

    def test_default_raw_provider_output_is_empty_dict(self):
        result = DetectionStageResult(
            object_type="facade",
            surface_condition=None,
            mask_polygon=None,
            area_confidence=0.0,
        )
        assert result.raw_provider_output == {}

    def test_accepts_polygon(self):
        polygon = [{"x": 0.1, "y": 0.2}, {"x": 0.9, "y": 0.8}]
        result = DetectionStageResult(
            object_type="roof",
            surface_condition="critical",
            mask_polygon=polygon,
            area_confidence=0.5,
        )
        assert result.mask_polygon == polygon


class TestExtractionStageResult:
    def test_is_frozen(self):
        detection = DetectionStageResult("roof", None, None, 0.5)
        extraction = ExtractionStageResult(
            detection=detection,
            estimated_area_sqm=100.0,
            estimated_unit="m2",
            recommended_scope="local_repair",
            materials=[],
            workflow_steps=[],
            estimated_total_days=None,
            labor_hours_total=None,
            catalog_attributes={},
        )
        with pytest.raises((AttributeError, TypeError)):
            extraction.estimated_area_sqm = 200.0  # type: ignore[misc]

    def test_back_reference_to_detection(self):
        detection = DetectionStageResult("facade", "good", None, 0.8)
        extraction = ExtractionStageResult(
            detection=detection,
            estimated_area_sqm=50.0,
            estimated_unit="m2",
            recommended_scope=None,
            materials=[],
            workflow_steps=[],
            estimated_total_days=None,
            labor_hours_total=None,
            catalog_attributes={},
        )
        assert extraction.detection is detection


class TestWorkCatalogMappingResult:
    def test_is_frozen(self):
        detection = DetectionStageResult("roof", None, None, 0.5)
        extraction = ExtractionStageResult(detection, None, "m2", None, [], [], None, None, {})
        mapping = WorkCatalogMappingResult(
            extraction=extraction,
            resolved_work_type_code="roof-repair",
            analysis_profile_code="standard",
            analysis_profile_version="1.0",
            estimated_quantity=100.0,
            estimated_unit="m2",
            validation_warnings=[],
        )
        with pytest.raises((AttributeError, TypeError)):
            mapping.resolved_work_type_code = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _decompose_legacy_output / LegacyProviderAdapter
# ---------------------------------------------------------------------------

class TestDecomposeLegacyOutput:
    def test_full_output_maps_to_all_stages(self):
        result = _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")

        assert isinstance(result, PipelineRunResult)
        assert result.provider_key == "mock"
        assert result.job_type == "vision_mock"
        assert result.model_name == "mock-vision"
        assert result.model_version == "0.3"

    def test_detection_stage_values(self):
        result = _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")

        assert result.detection.object_type == "roof"
        assert result.detection.surface_condition == "requires_attention"
        assert result.detection.area_confidence == pytest.approx(0.78)
        assert len(result.detection.mask_polygon) == 2

    def test_extraction_stage_values(self):
        result = _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")

        assert result.extraction.estimated_area_sqm == pytest.approx(85.5)
        assert result.extraction.estimated_unit == "m2"
        assert result.extraction.recommended_scope == "local_repair"
        assert len(result.extraction.materials) == 1
        assert len(result.extraction.workflow_steps) == 1
        assert result.extraction.estimated_total_days == pytest.approx(2.5)
        assert result.extraction.labor_hours_total == pytest.approx(8.0)
        assert "roof_pitch_deg" in result.extraction.catalog_attributes

    def test_mapping_stage_values(self):
        result = _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")

        assert result.mapping.resolved_work_type_code == "roof-repair"
        assert result.mapping.analysis_profile_code == "standard-roof"
        assert result.mapping.analysis_profile_version == "1.2"
        assert result.mapping.estimated_quantity == pytest.approx(85.5)
        assert result.mapping.validation_warnings == []

    def test_missing_objectType_defaults_to_other(self):
        raw = {**_FULL_PROVIDER_OUTPUT, "objectType": None}
        result = _decompose_legacy_output(raw, provider_key="mock")
        assert result.detection.object_type == "other"

    def test_missing_area_confidence_defaults_to_zero(self):
        raw = {k: v for k, v in _FULL_PROVIDER_OUTPUT.items() if k != "areaConfidence"}
        result = _decompose_legacy_output(raw, provider_key="mock")
        assert result.detection.area_confidence == 0.0

    def test_empty_provider_output_has_safe_defaults(self):
        result = _decompose_legacy_output({}, provider_key="stub")

        assert result.provider_key == "stub"
        assert result.detection.object_type == "other"
        assert result.detection.surface_condition is None
        assert result.detection.mask_polygon is None
        assert result.extraction.estimated_area_sqm is None
        assert result.extraction.materials == []
        assert result.extraction.workflow_steps == []
        assert result.mapping.resolved_work_type_code is None
        assert result.mapping.validation_warnings == []

    def test_estimatedQuantity_falls_back_to_estimatedAreaSqm(self):
        raw = {k: v for k, v in _FULL_PROVIDER_OUTPUT.items() if k != "estimatedQuantity"}
        result = _decompose_legacy_output(raw, provider_key="mock")
        assert result.mapping.estimated_quantity == pytest.approx(85.5)

    def test_raw_provider_output_preserved_on_detection(self):
        result = _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")
        assert result.detection.raw_provider_output is _FULL_PROVIDER_OUTPUT


class TestLegacyProviderAdapter:
    @pytest.mark.asyncio
    async def test_delegates_to_analyze_project(self):
        fake_provider = AsyncMock()
        fake_provider.key = "fake"
        fake_provider.analyze_project = AsyncMock(return_value=dict(_FULL_PROVIDER_OUTPUT))

        adapter = LegacyProviderAdapter(fake_provider)
        result = await adapter.run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        fake_provider.analyze_project.assert_awaited_once()
        assert isinstance(result, PipelineRunResult)
        assert result.detection.object_type == "roof"

    @pytest.mark.asyncio
    async def test_provider_key_from_provider_attribute(self):
        fake_provider = AsyncMock()
        fake_provider.key = "my-provider"
        fake_provider.analyze_project = AsyncMock(return_value={})

        adapter = LegacyProviderAdapter(fake_provider)
        result = await adapter.run(project={}, photos=[], analysis_config=None)

        assert result.provider_key == "my-provider"


# ---------------------------------------------------------------------------
# PipelineRunResult.to_legacy_dict()
# ---------------------------------------------------------------------------

class TestPipelineRunResultToLegacyDict:
    def _build_result(self) -> PipelineRunResult:
        return _decompose_legacy_output(_FULL_PROVIDER_OUTPUT, provider_key="mock")

    def test_all_expected_keys_present(self):
        legacy = self._build_result().to_legacy_dict()
        expected_keys = {
            "providerKey", "jobType", "objectType", "surfaceCondition", "maskPolygon",
            "areaConfidence", "recommendedScope", "estimatedAreaSqm", "estimatedUnit",
            "estimatedQuantity", "materials", "workflowSteps", "estimatedTotalDays",
            "laborHoursTotal", "catalogAttributes", "resolvedWorkTypeCode",
            "analysisProfileCode", "analysisProfileVersion", "validationWarnings",
            "modelName", "modelVersion",
        }
        assert expected_keys.issubset(legacy.keys())

    def test_values_roundtrip_through_stages(self):
        legacy = self._build_result().to_legacy_dict()

        assert legacy["objectType"] == "roof"
        assert legacy["surfaceCondition"] == "requires_attention"
        assert legacy["estimatedAreaSqm"] == pytest.approx(85.5)
        assert legacy["areaConfidence"] == pytest.approx(0.78)
        assert legacy["resolvedWorkTypeCode"] == "roof-repair"
        assert legacy["modelName"] == "mock-vision"
        assert legacy["modelVersion"] == "0.3"

    def test_empty_result_returns_safe_dict(self):
        result = _decompose_legacy_output({}, provider_key="stub")
        legacy = result.to_legacy_dict()

        assert legacy["objectType"] == "other"
        assert legacy["estimatedAreaSqm"] is None
        assert legacy["materials"] == []
        assert legacy["validationWarnings"] == []


# ---------------------------------------------------------------------------
# _is_staged routing
# ---------------------------------------------------------------------------

class TestIsStagedRouting:
    def test_legacy_provider_is_not_staged(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider
        assert _is_staged(MockVisionProvider()) is False

    def test_object_without_protocol_methods_is_not_staged(self):
        class PlainObject:
            key = "plain"
        assert _is_staged(PlainObject()) is False

    def test_object_implementing_all_staged_methods_is_staged(self):
        class FullyStagedProvider:
            key = "staged-stub"
            model_name = "stub"
            model_version = "0.1"

            async def detect(self, *, project, photos, analysis_config):
                ...

            async def extract(self, *, project, photos, detection, analysis_config):
                ...

            async def map_to_catalog(self, *, extraction, analysis_config):
                ...

        assert _is_staged(FullyStagedProvider()) is True


# ---------------------------------------------------------------------------
# PipelineOrchestrator — legacy path
# ---------------------------------------------------------------------------

class TestPipelineOrchestratorLegacyPath:
    @pytest.mark.asyncio
    async def test_routes_to_legacy_adapter_for_mock_provider(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        provider = MockVisionProvider()
        orchestrator = PipelineOrchestrator(provider)
        assert orchestrator._is_staged is False

        result = await orchestrator.run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert isinstance(result, PipelineRunResult)
        assert result.provider_key == "mock"

    @pytest.mark.asyncio
    async def test_legacy_result_contains_all_stage_results(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        result = await PipelineOrchestrator(MockVisionProvider()).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert isinstance(result.detection, DetectionStageResult)
        assert isinstance(result.extraction, ExtractionStageResult)
        assert isinstance(result.mapping, WorkCatalogMappingResult)

    @pytest.mark.asyncio
    async def test_detection_object_type_from_mock_project(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        # mock provider checks for the exact string "strecha" (nominative)
        result = await PipelineOrchestrator(MockVisionProvider()).run(
            project={"description": "oprava strecha", "address_label": "Brno"},
            photos=_make_photos(),
            analysis_config=None,
        )

        assert result.detection.object_type == "roof"

    @pytest.mark.asyncio
    async def test_facade_project_detection(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        result = await PipelineOrchestrator(MockVisionProvider()).run(
            project={"description": "oprava fasady", "address_label": "Ostrava"},
            photos=_make_photos(),
            analysis_config=None,
        )

        assert result.detection.object_type == "facade"

    @pytest.mark.asyncio
    async def test_extraction_has_non_empty_materials(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        result = await PipelineOrchestrator(MockVisionProvider()).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert len(result.extraction.materials) > 0
        assert len(result.extraction.workflow_steps) > 0

    @pytest.mark.asyncio
    async def test_area_confidence_within_bounds(self):
        from app.ai.providers.mock_vision_provider import MockVisionProvider

        result = await PipelineOrchestrator(MockVisionProvider()).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert 0.0 <= result.detection.area_confidence <= 1.0


# ---------------------------------------------------------------------------
# PipelineOrchestrator — staged path
# ---------------------------------------------------------------------------

class TestPipelineOrchestratorStagedPath:
    """Test the orchestrator using a synthetic staged provider."""

    def _build_staged_provider(
        self,
        *,
        detect_result: DetectionStageResult | None = None,
        extract_result: ExtractionStageResult | None = None,
        map_result: WorkCatalogMappingResult | None = None,
    ):
        default_detection = DetectionStageResult(
            object_type="roof",
            surface_condition="good",
            mask_polygon=None,
            area_confidence=0.9,
        )
        detection = detect_result or default_detection
        extraction = extract_result or ExtractionStageResult(
            detection=detection,
            estimated_area_sqm=120.0,
            estimated_unit="m2",
            recommended_scope="local_repair",
            materials=[{"name": "Test", "unit": "kg", "quantity": 5.0, "unitPrice": 10.0, "totalPrice": 50.0}],
            workflow_steps=[{"step": 1, "name": "Test step", "description": "x", "estimatedHours": 2}],
            estimated_total_days=1.0,
            labor_hours_total=2.0,
            catalog_attributes={"test_attr": {"value": 42, "confidence": 0.8}},
        )
        mapping = map_result or WorkCatalogMappingResult(
            extraction=extraction,
            resolved_work_type_code="roof-repair",
            analysis_profile_code="test-profile",
            analysis_profile_version="2.0",
            estimated_quantity=120.0,
            estimated_unit="m2",
            validation_warnings=["test warning"],
        )

        class StagedStub:
            key = "staged-stub"
            model_name = "staged-model"
            model_version = "1.0"

            async def detect(self, *, project, photos, analysis_config):
                return detection

            async def extract(self, *, project, photos, detection, analysis_config):
                return extraction

            async def map_to_catalog(self, *, extraction, analysis_config):
                return mapping

        return StagedStub()

    def test_staged_provider_is_detected_as_staged(self):
        provider = self._build_staged_provider()
        orchestrator = PipelineOrchestrator(provider)
        assert orchestrator._is_staged is True

    @pytest.mark.asyncio
    async def test_staged_path_returns_pipeline_run_result(self):
        provider = self._build_staged_provider()
        result = await PipelineOrchestrator(provider).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert isinstance(result, PipelineRunResult)
        assert result.provider_key == "staged-stub"
        assert result.model_name == "staged-model"

    @pytest.mark.asyncio
    async def test_staged_path_uses_provider_stage_outputs(self):
        provider = self._build_staged_provider()
        result = await PipelineOrchestrator(provider).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )

        assert result.detection.object_type == "roof"
        assert result.detection.area_confidence == pytest.approx(0.9)
        assert result.extraction.estimated_area_sqm == pytest.approx(120.0)
        assert result.mapping.resolved_work_type_code == "roof-repair"
        assert result.mapping.validation_warnings == ["test warning"]

    @pytest.mark.asyncio
    async def test_staged_path_to_legacy_dict_has_all_keys(self):
        provider = self._build_staged_provider()
        result = await PipelineOrchestrator(provider).run(
            project=_make_project(),
            photos=_make_photos(),
            analysis_config=None,
        )
        legacy = result.to_legacy_dict()

        assert legacy["objectType"] == "roof"
        assert legacy["estimatedAreaSqm"] == pytest.approx(120.0)
        assert legacy["resolvedWorkTypeCode"] == "roof-repair"
        assert legacy["validationWarnings"] == ["test warning"]
        assert legacy["modelName"] == "staged-model"

    @pytest.mark.asyncio
    async def test_staged_detect_receives_analysis_config(self):
        detect_calls = []

        class InstrumentedStaged:
            key = "instrumented"
            model_name = "x"
            model_version = "0"

            async def detect(self, *, project, photos, analysis_config):
                detect_calls.append(analysis_config)
                return DetectionStageResult("facade", None, None, 0.5)

            async def extract(self, *, project, photos, detection, analysis_config):
                return ExtractionStageResult(detection, None, "m2", None, [], [], None, None, {})

            async def map_to_catalog(self, *, extraction, analysis_config):
                return WorkCatalogMappingResult(extraction, None, None, None, None, "m2", [])

        config = {"workTypeCode": "facade-repair"}
        await PipelineOrchestrator(InstrumentedStaged()).run(
            project={},
            photos=[],
            analysis_config=config,
        )

        assert detect_calls == [config]


# ---------------------------------------------------------------------------
# run_project_analysis() backward-compat integration
# ---------------------------------------------------------------------------

class TestRunProjectAnalysisBackwardCompat:
    """Verify that the updated run_project_analysis() returns the same keys
    as before — downstream (AnalysisService, repository) must not change."""

    EXPECTED_KEYS = {
        "providerKey", "jobType", "objectType", "surfaceCondition",
        "recommendedScope", "estimatedQuantity", "estimatedUnit",
        "estimatedAreaSqm", "areaConfidence", "maskPolygon",
        "materials", "workflowSteps", "estimatedTotalDays", "laborHoursTotal",
        "catalogAttributes", "validationWarnings", "analysisProfileCode",
        "analysisProfileVersion", "resolvedWorkTypeCode", "modelName", "modelVersion",
    }

    @pytest.mark.asyncio
    async def test_mock_provider_returns_all_expected_keys(self):
        from app.ai.analysis_service import run_project_analysis

        # Patch normalize_photo_inputs to avoid real DB/storage access
        with patch(
            "app.ai.analysis_service.normalize_photo_inputs",
            new=AsyncMock(return_value=_make_photos()),
        ):
            result = await run_project_analysis(
                provider_key="mock",
                project=_make_project(),
                photos=[],
                analysis_config=None,
            )

        assert self.EXPECTED_KEYS.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_mock_provider_objectType_is_string(self):
        from app.ai.analysis_service import run_project_analysis

        with patch(
            "app.ai.analysis_service.normalize_photo_inputs",
            new=AsyncMock(return_value=_make_photos()),
        ):
            result = await run_project_analysis(
                provider_key="mock",
                project=_make_project(),
                photos=[],
                analysis_config=None,
            )

        assert isinstance(result["objectType"], str)

    @pytest.mark.asyncio
    async def test_mock_provider_materials_is_list(self):
        from app.ai.analysis_service import run_project_analysis

        with patch(
            "app.ai.analysis_service.normalize_photo_inputs",
            new=AsyncMock(return_value=_make_photos()),
        ):
            result = await run_project_analysis(
                provider_key="mock",
                project=_make_project(),
                photos=[],
                analysis_config=None,
            )

        assert isinstance(result["materials"], list)
        assert len(result["materials"]) > 0

    @pytest.mark.asyncio
    async def test_with_analysis_profile_config(self):
        from app.ai.analysis_service import run_project_analysis

        config = {
            "workTypeCode": "roof-repair",
            "analysisProfile": {
                "code": "roof-v2",
                "version": "2",
                "extractionRules": [
                    {"attributeCode": "pitch_deg", "dataType": "number", "sourceObjectCode": "roof"}
                ],
            },
        }

        with patch(
            "app.ai.analysis_service.normalize_photo_inputs",
            new=AsyncMock(return_value=_make_photos()),
        ):
            result = await run_project_analysis(
                provider_key="mock",
                project={"description": "strecha", "address_label": "Praha"},
                photos=[],
                analysis_config=config,
            )

        assert result["analysisProfileCode"] == "roof-v2"
        assert result["resolvedWorkTypeCode"] == "roof-repair"
        assert isinstance(result["catalogAttributes"], dict)

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        from app.ai.analysis_service import run_project_analysis

        with pytest.raises(ValueError, match="not supported"):
            await run_project_analysis(
                provider_key="nonexistent",
                project={},
                photos=[],
            )
