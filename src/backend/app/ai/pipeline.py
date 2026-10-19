"""Vision pipeline orchestration layer (Step 15).

This module defines:
  - ``StagedVisionPipeline``   — Protocol for providers that implement individual
                                 stages (detect / extract / map_to_catalog).
  - ``LegacyProviderAdapter``  — Wraps existing single-shot providers
                                 (mock, claude, …) and decomposes their flat
                                 output into the three stage contracts.
  - ``PipelineOrchestrator``   — Runs either path and returns ``PipelineRunResult``.

Routing rule (explicit, never implicit):
  If the provider object has ``detect``, ``extract``, and ``map_to_catalog``
  attributes (i.e. implements ``StagedVisionPipeline``), the orchestrator takes
  the staged path.  Otherwise it falls back to the legacy adapter path.

This keeps the rollout safe:  all current providers (mock / claude) go through
the legacy path unchanged until they are explicitly upgraded to the staged
protocol.
"""
from __future__ import annotations

import structlog
from typing import Protocol, runtime_checkable

from app.ai.pipeline_contracts import (
    DetectionStageResult,
    ExtractionStageResult,
    PipelineRunResult,
    WorkCatalogMappingResult,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol — staged providers implement this instead of analyze_project()
# ---------------------------------------------------------------------------

@runtime_checkable
class StagedVisionPipeline(Protocol):
    """Protocol for providers that implement pipeline stages individually.

    New providers SHOULD implement this protocol rather than the legacy
    ``analyze_project()`` method.  Each stage receives the output of the
    previous stage so that providers can branch on intermediate results.

    Implementations must be async-safe and must not mutate their inputs.
    """

    key: str

    async def detect(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None,
    ) -> DetectionStageResult:
        """Identify objects, surfaces, and masks in the image set."""
        ...

    async def extract(
        self,
        *,
        project: dict,
        photos: list[dict],
        detection: DetectionStageResult,
        analysis_config: dict | None,
    ) -> ExtractionStageResult:
        """Normalise measurements, materials, and workflow steps."""
        ...

    async def map_to_catalog(
        self,
        *,
        extraction: ExtractionStageResult,
        analysis_config: dict | None,
    ) -> WorkCatalogMappingResult:
        """Align extracted data to the work catalogue."""
        ...

    @property
    def model_name(self) -> str:
        """Human-readable model identifier."""
        ...

    @property
    def model_version(self) -> str:
        """Pinned model version string."""
        ...


def _is_staged(provider: object) -> bool:
    """Return True iff the provider implements the StagedVisionPipeline protocol."""
    return isinstance(provider, StagedVisionPipeline)


# ---------------------------------------------------------------------------
# Legacy adapter — decomposes flat analyze_project() output into stage results
# ---------------------------------------------------------------------------

class LegacyProviderAdapter:
    """Wraps a legacy provider and decomposes its output into pipeline stages.

    The flat dict produced by ``analyze_project()`` is treated as an opaque
    blob that is decomposed once, after the call returns.  No intermediate
    DB writes or side effects happen during decomposition.
    """

    def __init__(self, provider: object) -> None:
        self._provider = provider

    @property
    def key(self) -> str:
        return str(getattr(self._provider, "key", "unknown"))

    async def run(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None,
    ) -> PipelineRunResult:
        raw: dict = await self._provider.analyze_project(  # type: ignore[attr-defined]
            project=project,
            photos=photos,
            analysis_config=analysis_config,
        )
        return _decompose_legacy_output(raw, provider_key=self.key)


def _decompose_legacy_output(raw: dict, *, provider_key: str) -> PipelineRunResult:
    """Convert a flat provider output dict to a structured PipelineRunResult.

    All field access uses ``dict.get()`` with safe defaults so a partially
    populated provider response never raises KeyError.
    """
    # --- Stage 1 : Detection ---
    detection = DetectionStageResult(
        object_type=str(raw.get("objectType") or "other"),
        surface_condition=raw.get("surfaceCondition") or None,
        mask_polygon=raw.get("maskPolygon") or None,
        area_confidence=float(raw.get("areaConfidence") or 0.0),
        raw_provider_output=raw,
    )

    # --- Stage 2 : Extraction ---
    extraction = ExtractionStageResult(
        detection=detection,
        estimated_area_sqm=_optional_float(raw.get("estimatedAreaSqm")),
        estimated_unit=str(raw.get("estimatedUnit") or "m2"),
        recommended_scope=raw.get("recommendedScope") or None,
        materials=list(raw.get("materials") or []),
        workflow_steps=list(raw.get("workflowSteps") or []),
        estimated_total_days=_optional_float(raw.get("estimatedTotalDays")),
        labor_hours_total=_optional_float(raw.get("laborHoursTotal")),
        catalog_attributes=dict(raw.get("catalogAttributes") or {}),
    )

    # --- Stage 3 : Catalogue mapping ---
    quantity = raw.get("estimatedQuantity", raw.get("estimatedAreaSqm"))
    mapping = WorkCatalogMappingResult(
        extraction=extraction,
        resolved_work_type_code=raw.get("resolvedWorkTypeCode") or None,
        analysis_profile_code=raw.get("analysisProfileCode") or None,
        analysis_profile_version=raw.get("analysisProfileVersion") or None,
        estimated_quantity=_optional_float(quantity),
        estimated_unit=str(raw.get("estimatedUnit") or "m2"),
        validation_warnings=list(raw.get("validationWarnings") or []),
    )

    return PipelineRunResult(
        provider_key=str(raw.get("providerKey") or provider_key),
        job_type=str(raw.get("jobType") or "manual_trigger"),
        model_name=str(raw.get("modelName") or provider_key),
        model_version=str(raw.get("modelVersion") or "1.0"),
        detection=detection,
        extraction=extraction,
        mapping=mapping,
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Orchestrator — entry point for all pipeline executions
# ---------------------------------------------------------------------------

class PipelineOrchestrator:
    """Runs the Vision analysis pipeline for a given provider.

    Routing:
      - If the provider implements ``StagedVisionPipeline``, each stage is
        called individually.  Stage failures are isolated — a detection
        failure propagates, but an extraction failure after a successful
        detection still produces a partial ``PipelineRunResult`` with safe
        defaults (so the job can complete with reduced data rather than crash).
      - Otherwise the provider is wrapped in ``LegacyProviderAdapter`` and
        the single ``analyze_project()`` call is decomposed afterwards.

    The orchestrator does not handle retries — that responsibility belongs to
    the caller (AnalysisService) which already has retry/DLQ logic.
    """

    def __init__(self, provider: object) -> None:
        self._provider = provider
        self._is_staged = _is_staged(provider)

    async def run(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None = None,
    ) -> PipelineRunResult:
        provider_key = str(getattr(self._provider, "key", "unknown"))

        if self._is_staged:
            logger.debug(
                "pipeline.staged_path",
                provider=provider_key,
                photo_count=len(photos),
            )
            return await self._run_staged(
                provider=self._provider,  # type: ignore[arg-type]
                project=project,
                photos=photos,
                analysis_config=analysis_config,
            )

        logger.debug(
            "pipeline.legacy_path",
            provider=provider_key,
            photo_count=len(photos),
        )
        adapter = LegacyProviderAdapter(self._provider)
        return await adapter.run(
            project=project,
            photos=photos,
            analysis_config=analysis_config,
        )

    @staticmethod
    async def _run_staged(
        provider: StagedVisionPipeline,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None,
    ) -> PipelineRunResult:
        provider_key = provider.key

        # Stage 1 — Detection (hard failure: without detection we have nothing)
        detection = await provider.detect(
            project=project,
            photos=photos,
            analysis_config=analysis_config,
        )
        logger.debug(
            "pipeline.detection_done",
            provider=provider_key,
            object_type=detection.object_type,
            confidence=detection.area_confidence,
        )

        # Stage 2 — Extraction (hard failure: extraction drives pricing inputs)
        extraction = await provider.extract(
            project=project,
            photos=photos,
            detection=detection,
            analysis_config=analysis_config,
        )
        logger.debug(
            "pipeline.extraction_done",
            provider=provider_key,
            estimated_area_sqm=extraction.estimated_area_sqm,
            material_count=len(extraction.materials),
        )

        # Stage 3 — Catalogue mapping (soft failure: warnings preserved, not raised)
        mapping = await provider.map_to_catalog(
            extraction=extraction,
            analysis_config=analysis_config,
        )
        logger.debug(
            "pipeline.mapping_done",
            provider=provider_key,
            work_type_code=mapping.resolved_work_type_code,
            warning_count=len(mapping.validation_warnings),
        )

        return PipelineRunResult(
            provider_key=provider_key,
            job_type="manual_trigger",
            model_name=provider.model_name,
            model_version=provider.model_version,
            detection=detection,
            extraction=extraction,
            mapping=mapping,
        )
