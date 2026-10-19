"""Inter-stage data contracts for the Vision analysis pipeline.

Each stage in the pipeline produces a frozen, immutable result that is passed to
the next stage. This makes the data flow explicit and auditable.

Stage order:
  1. Detection   — what physical objects / surfaces are present and where
  2. Extraction  — normalised measurements, materials, workflow steps
  3. Mapping     — catalogue alignment (work-type code, profile, parameters)

A fourth Pricing stage exists conceptually but is intentionally omitted here:
pricing interpretation is owned by QuoteVariantService downstream and pulling it
into the Vision layer would require coupling to quote logic that is not yet stable.

All contracts use frozen dataclasses so that intermediate results cannot be
mutated after production. The `raw_provider_output` field on DetectionStageResult
is the escape hatch for provider-specific data that does not fit the contract —
it is preserved for debugging but must not be relied upon by downstream stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Stage 1 — Detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DetectionStageResult:
    """Output of the detection stage.

    Captures what the vision model identified in the image set.
    Coordinates in mask_polygon are normalised (0.0–1.0 relative to image
    dimensions) so they are resolution-independent.
    """

    object_type: str
    """Coarse object category: 'roof', 'facade', 'interior', 'foundation', 'other'."""

    surface_condition: str | None
    """Coarse condition: 'good', 'requires_attention', 'critical', or None."""

    mask_polygon: list[dict] | None
    """Normalised polygon points [{x, y}] or None when unavailable."""

    area_confidence: float
    """Confidence in the detected area estimate (0.0–1.0)."""

    raw_provider_output: dict = field(default_factory=dict)
    """Passthrough of the provider's raw output dict.  Do not couple to this."""


# ---------------------------------------------------------------------------
# Stage 2 — Extraction / Normalisation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractionStageResult:
    """Output of the extraction stage.

    Transforms the raw detection into normalised, unit-safe measurements and
    structured lists ready for catalogue mapping.
    """

    detection: DetectionStageResult
    """Back-reference to the detection result that fed this stage."""

    estimated_area_sqm: float | None
    """Best-effort area estimate in m²; None when cannot be determined."""

    estimated_unit: str
    """Unit of the primary quantity estimate ('m2', 'ks', 'bm', …)."""

    recommended_scope: str | None
    """Recommended repair scope: 'cleaning', 'local_repair', 'full_reconstruction'."""

    materials: list[dict]
    """Structured material list [{name, unit, quantity, unitPrice, totalPrice}]."""

    workflow_steps: list[dict]
    """Ordered workflow steps [{step, name, description, estimatedHours}]."""

    estimated_total_days: float | None
    """Total calendar days estimate; None when unavailable."""

    labor_hours_total: float | None
    """Total labour hours across all workflow steps; None when unavailable."""

    catalog_attributes: dict
    """Extracted catalogue attributes keyed by attribute_code."""


# ---------------------------------------------------------------------------
# Stage 3 — Work-Catalogue Mapping
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkCatalogMappingResult:
    """Output of the catalogue-mapping stage.

    Aligns extracted data to the work catalogue: work type, analysis profile,
    and the primary quantity that will drive pricing.
    """

    extraction: ExtractionStageResult
    """Back-reference to the extraction result that fed this stage."""

    resolved_work_type_code: str | None
    """Catalogue work-type code resolved from the extraction or config."""

    analysis_profile_code: str | None
    """Analysis profile code used for attribute extraction rules."""

    analysis_profile_version: str | None
    """Pinned profile version at the time of analysis."""

    estimated_quantity: float | None
    """Primary quantity to be priced (often == estimated_area_sqm but can differ)."""

    estimated_unit: str
    """Unit for estimated_quantity."""

    validation_warnings: list[str]
    """Non-fatal issues found during mapping (missing profile, unknown work type, …)."""


# ---------------------------------------------------------------------------
# Aggregated pipeline result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineRunResult:
    """Aggregated result of a complete pipeline run.

    Wraps all three stage results together with provider metadata.  The
    ``to_legacy_dict()`` method converts this back to the flat dict format
    expected by the rest of the application (AnalysisService, repository),
    keeping the pipeline layer transparent to downstream code.
    """

    provider_key: str
    job_type: str
    model_name: str
    model_version: str
    detection: DetectionStageResult
    extraction: ExtractionStageResult
    mapping: WorkCatalogMappingResult

    def to_legacy_dict(self) -> dict:
        """Convert to the flat dict format consumed by AnalysisService / repository."""
        return {
            "providerKey": self.provider_key,
            "jobType": self.job_type,
            "objectType": self.detection.object_type,
            "surfaceCondition": self.detection.surface_condition,
            "maskPolygon": self.detection.mask_polygon,
            "areaConfidence": self.detection.area_confidence,
            "recommendedScope": self.extraction.recommended_scope,
            "estimatedAreaSqm": self.extraction.estimated_area_sqm,
            "estimatedUnit": self.extraction.estimated_unit,
            "estimatedQuantity": self.mapping.estimated_quantity,
            "materials": self.extraction.materials,
            "workflowSteps": self.extraction.workflow_steps,
            "estimatedTotalDays": self.extraction.estimated_total_days,
            "laborHoursTotal": self.extraction.labor_hours_total,
            "catalogAttributes": self.extraction.catalog_attributes,
            "resolvedWorkTypeCode": self.mapping.resolved_work_type_code,
            "analysisProfileCode": self.mapping.analysis_profile_code,
            "analysisProfileVersion": self.mapping.analysis_profile_version,
            "validationWarnings": self.mapping.validation_warnings,
            "modelName": self.model_name,
            "modelVersion": self.model_version,
        }
