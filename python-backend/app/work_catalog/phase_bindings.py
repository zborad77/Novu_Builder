"""Work-type → case-phase binding registry.

Declares which case statuses each work type is relevant in, whether it is
recommended for UI surfacing in a given phase, and whether AI Vision can
produce detections for it.

Rules
-----
allowed_in      — case statuses where a ProjectWorkItem of this type may be
                  created or edited.  Attempting to add a work item outside
                  this set must be rejected.

recommended_in  — statuses where the UI or AI should prominently surface this
                  type.  A superset of the states where the type is actually
                  useful; used for catalog pre-filtering.

vision_detectable — True ↔ the type has an AnalysisProfile and can appear as
                  a VisionDetection.  Only these codes are valid in pipeline
                  mapping output.  If AI returns a non-detectable code, it is
                  treated as a pipeline anomaly.

Coverage contract
-----------------
This module is imported by seeds._validate_catalog_seed() which asserts that
every work type code in CATALOG_SEED has an entry here and no entry is stale.
Add new entries here whenever a new work type is added to seeds.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.case_workflow.transitions import VALID_STATUSES

# ---------------------------------------------------------------------------
# Phase sets — reused across entries to keep the table readable.
# ---------------------------------------------------------------------------

#: States where work items are actively created / edited (all pre-terminal states).
_ACTIVE: frozenset[str] = frozenset({
    "draft", "intake", "analyzing", "proposal_ready", "quote_ready",
})

#: States where AI-detected types are shown after detection phase.
_REPAIR_REC: frozenset[str] = frozenset({"analyzing", "proposal_ready"})

#: States where non-AI installation types are shown.
_INSTALL_REC: frozenset[str] = frozenset({"draft", "intake", "proposal_ready"})

#: Triage-relevant types (inspection / emergency) — surface from intake.
_TRIAGE_REC: frozenset[str] = frozenset({"intake", "analyzing", "proposal_ready"})

#: Inspection-only types — surface during intake & analysis review.
_INSPECT_REC: frozenset[str] = frozenset({"intake", "analyzing"})

#: Post-completion service types.
_POST_REC: frozenset[str] = frozenset({"proposal_ready", "quote_ready"})


# ---------------------------------------------------------------------------
# Binding type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkTypePhaseBinding:
    allowed_in: frozenset[str]
    recommended_in: frozenset[str]
    vision_detectable: bool


def _v(rec: frozenset[str]) -> WorkTypePhaseBinding:
    """Shorthand: vision-detectable, allowed in all active states."""
    return WorkTypePhaseBinding(allowed_in=_ACTIVE, recommended_in=rec, vision_detectable=True)


def _m(rec: frozenset[str]) -> WorkTypePhaseBinding:
    """Shorthand: manual-only (no vision), allowed in all active states."""
    return WorkTypePhaseBinding(allowed_in=_ACTIVE, recommended_in=rec, vision_detectable=False)


# ---------------------------------------------------------------------------
# Registry — keyed by WorkType.code  (matches seeds._WORK_TYPES[*]["code"])
# ---------------------------------------------------------------------------

PHASE_BINDINGS: dict[str, WorkTypePhaseBinding] = {

    # ── masonry-structural ──────────────────────────────────────────────
    "chimney-renovation":      _v(_REPAIR_REC),
    "chimney-new-build":       _m(_INSTALL_REC),
    "wall-construction":       _m(_INSTALL_REC),
    "wall-demolition":         _v(_REPAIR_REC),
    "plastering":              _v(_REPAIR_REC),
    "facade-installation":     _v(_REPAIR_REC),
    "insulation-installation": _m(_INSTALL_REC),
    "foundation-work":         _m(_INSTALL_REC),

    # ── floors-paving ───────────────────────────────────────────────────
    "pedestal-paving":          _m(_INSTALL_REC),
    "tile-installation":        _m(_INSTALL_REC),
    "floor-renovation":         _v(_REPAIR_REC),
    "vinyl-floor-installation": _m(_INSTALL_REC),
    "wood-floor-installation":  _m(_INSTALL_REC),
    "concrete-floor":           _m(_INSTALL_REC),

    # ── roofing ─────────────────────────────────────────────────────────
    "roof-repair":      _v(_REPAIR_REC),
    "roof-installation":_m(_INSTALL_REC),
    "roof-inspection":  _m(_INSPECT_REC),
    "gutter-installation": _m(_INSTALL_REC),
    "gutter-repair":    _v(_REPAIR_REC),
    "roof-insulation":  _m(_INSTALL_REC),

    # ── windows-doors ───────────────────────────────────────────────────
    "window-installation": _m(_INSTALL_REC),
    "window-replacement":  _v(_REPAIR_REC),
    "door-installation":   _m(_INSTALL_REC),
    "door-repair":         _v(_REPAIR_REC),

    # ── electrical ──────────────────────────────────────────────────────
    "electrical-installation": _m(_INSTALL_REC),
    "electrical-repair":       _m(_REPAIR_REC),

    # ── plumbing ────────────────────────────────────────────────────────
    "plumbing-installation": _m(_INSTALL_REC),
    "plumbing-repair":       _m(_REPAIR_REC),

    # ── heating ─────────────────────────────────────────────────────────
    "heating-installation":  _m(_INSTALL_REC),
    "boiler-installation":   _m(_INSTALL_REC),
    "radiator-installation": _m(_INSTALL_REC),

    # ── finishing ───────────────────────────────────────────────────────
    "painting":           _v(_REPAIR_REC),
    "interior-finishing": _v(_REPAIR_REC),
    "drywall-installation": _m(_INSTALL_REC),
    "ceiling-installation": _m(_INSTALL_REC),

    # ── exterior ────────────────────────────────────────────────────────
    "terrace-construction": _m(_INSTALL_REC),
    "fence-installation":   _m(_INSTALL_REC),
    "driveway-paving":      _m(_INSTALL_REC),
    "garden-landscaping":   _m(_INSTALL_REC),

    # ── inspection-service ──────────────────────────────────────────────
    "inspection":                  _m(_INSPECT_REC),
    "maintenance":                 _m(_POST_REC),
    "cleaning-after-construction": _m(_POST_REC),
    "emergency-repair":            _v(_TRIAGE_REC),

    # ── roofing — granular tree types ───────────────────────────────────
    "roof-cover-installation":      _m(_INSTALL_REC),
    "roof-cover-replacement":       _m(_REPAIR_REC),
    "roof-cover-cleaning":          _m(_POST_REC),
    "roof-truss-new":               _m(_INSTALL_REC),
    "roof-truss-repair":            _m(_REPAIR_REC),
    "roof-truss-reconstruction":    _m(_INSTALL_REC),
    "roof-truss-reinforcement":     _m(_REPAIR_REC),
    "roof-insulation-repair":       _m(_REPAIR_REC),
    "roof-insulation-replacement":  _m(_INSTALL_REC),
    "gutter-replacement":           _m(_INSTALL_REC),
    "gutter-cleaning":              _m(_POST_REC),
    "skylight-installation":        _m(_INSTALL_REC),
    "skylight-repair":              _m(_REPAIR_REC),
    "skylight-replacement":         _m(_INSTALL_REC),

    # ── masonry-structural — facade granular ─────────────────────────────
    "facade-plaster-repair":            _m(_REPAIR_REC),
    "facade-plaster-reconstruction":    _m(_INSTALL_REC),
    "facade-insulation-repair":         _m(_REPAIR_REC),
    "facade-insulation-reconstruction": _m(_INSTALL_REC),
    "facade-coating-renewal":           _m(_REPAIR_REC),
    "facade-crack-repair":              _m(_REPAIR_REC),
    "facade-crack-remediation":         _m(_REPAIR_REC),

    # ── masonry-structural — chimney granular ────────────────────────────
    "chimney-body-repair":           _m(_REPAIR_REC),
    "chimney-body-removal":          _m(_REPAIR_REC),
    "chimney-lining-installation":   _m(_INSTALL_REC),
    "chimney-lining-replacement":    _m(_INSTALL_REC),
    "chimney-lining-repair":         _m(_REPAIR_REC),
    "chimney-plaster-new":           _m(_INSTALL_REC),
    "chimney-plaster-repair":        _m(_REPAIR_REC),
    "chimney-head-repair":           _m(_REPAIR_REC),
    "chimney-head-reconstruction":   _m(_INSTALL_REC),
    "chimney-head-cap-installation": _m(_INSTALL_REC),

    # ── masonry-structural — foundation granular ─────────────────────────
    "foundation-waterproofing-new":        _m(_INSTALL_REC),
    "foundation-waterproofing-repair":     _m(_REPAIR_REC),
    "foundation-masonry-repair":           _m(_REPAIR_REC),
    "foundation-moisture-remediation":     _m(_REPAIR_REC),
    "foundation-drainage-installation":    _m(_INSTALL_REC),
    "foundation-drainage-repair":          _m(_REPAIR_REC),

    # ── windows-doors — granular ─────────────────────────────────────────
    "window-repair":        _m(_REPAIR_REC),
    "window-adjustment":    _m(_REPAIR_REC),
    "door-replacement":     _m(_INSTALL_REC),
    "sealing-installation": _m(_INSTALL_REC),
    "sealing-replacement":  _m(_REPAIR_REC),

    # ── exterior — balcony / terrace granular ────────────────────────────
    "balcony-waterproofing-new":            _m(_INSTALL_REC),
    "balcony-waterproofing-repair":         _m(_REPAIR_REC),
    "balcony-waterproofing-reconstruction": _m(_INSTALL_REC),
    "balcony-surface-installation":         _m(_INSTALL_REC),
    "balcony-surface-repair":               _m(_REPAIR_REC),
    "balcony-surface-replacement":          _m(_INSTALL_REC),
    "balcony-railing-installation":         _m(_INSTALL_REC),
    "balcony-railing-repair":               _m(_REPAIR_REC),
    "balcony-railing-replacement":          _m(_INSTALL_REC),

    # ── finishing — interior granular ────────────────────────────────────
    "interior-wall-repair":        _m(_REPAIR_REC),
    "interior-floor-installation": _m(_INSTALL_REC),
    "interior-floor-replacement":  _m(_INSTALL_REC),
    "interior-ceiling-repair":     _m(_REPAIR_REC),
    "interior-ceiling-lowering":   _m(_INSTALL_REC),
}


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------

def get_phase_binding(work_type_code: str) -> WorkTypePhaseBinding | None:
    return PHASE_BINDINGS.get(work_type_code)


def is_allowed_in_status(work_type_code: str, case_status: str) -> bool:
    """Return True if a work item of *work_type_code* may exist in *case_status*."""
    b = PHASE_BINDINGS.get(work_type_code)
    return b is not None and case_status in b.allowed_in


def get_recommended_work_type_codes(case_status: str) -> list[str]:
    """Return sorted work type codes recommended for the given case status."""
    return sorted(
        code for code, b in PHASE_BINDINGS.items()
        if case_status in b.recommended_in
    )


def get_allowed_work_type_codes(case_status: str) -> list[str]:
    """Return sorted work type codes allowed in the given case status."""
    return sorted(
        code for code, b in PHASE_BINDINGS.items()
        if case_status in b.allowed_in
    )


def is_recommended_in_status(work_type_code: str, case_status: str) -> bool:
    """Return True if the work type should be surfaced in the given case status."""
    binding = PHASE_BINDINGS.get(work_type_code)
    return binding is not None and case_status in binding.recommended_in


def get_vision_detectable_codes() -> list[str]:
    """Return sorted codes of work types that AI Vision can produce detections for."""
    return sorted(code for code, b in PHASE_BINDINGS.items() if b.vision_detectable)


# ---------------------------------------------------------------------------
# Import-time self-check — catches stale / missing entries without a DB.
# ---------------------------------------------------------------------------

_KNOWN_CODES: frozenset[str] = frozenset(PHASE_BINDINGS)

def _assert_binding_coverage(work_type_codes: frozenset[str]) -> None:
    """Called by seeds._validate_catalog_seed() to enforce full coverage."""
    missing = work_type_codes - _KNOWN_CODES
    extra = _KNOWN_CODES - work_type_codes
    if missing:
        raise AssertionError(
            f"Work types without phase bindings (add to phase_bindings.py): {sorted(missing)}"
        )
    if extra:
        raise AssertionError(
            f"Phase bindings for unknown work types (remove from phase_bindings.py): {sorted(extra)}"
        )

    invalid_allowed_states: dict[str, list[str]] = {}
    invalid_recommended_states: dict[str, list[str]] = {}
    for code, binding in PHASE_BINDINGS.items():
        bad_allowed = sorted(state for state in binding.allowed_in if state not in VALID_STATUSES)
        bad_recommended = sorted(state for state in binding.recommended_in if state not in VALID_STATUSES)
        if bad_allowed:
            invalid_allowed_states[code] = bad_allowed
        if bad_recommended:
            invalid_recommended_states[code] = bad_recommended

    if invalid_allowed_states:
        raise AssertionError(
            f"Phase bindings contain invalid allowed_in states: {invalid_allowed_states}"
        )
    if invalid_recommended_states:
        raise AssertionError(
            f"Phase bindings contain invalid recommended_in states: {invalid_recommended_states}"
        )
