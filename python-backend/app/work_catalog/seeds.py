"""
Global work catalog seed data — single authoritative source of truth for all catalog definitions.

Structure
---------
CATALOG_SEED            — pure global catalog (categories, profiles, work types, parameters, options).
                          Safe to load in any environment.
GLOBAL_WORK_CATALOG_SEED — CATALOG_SEED + dev/test tenant overrides.
                          Used by bootstrap.py for local development.

How to add a new work type
--------------------------
1.  Pick or create a category in _CATEGORIES (stable ID, code, sort_order).
2.  Add a row to _WORK_TYPES (new stable ID, category_id, code, default_unit, measurement_kind).
3.  Add at least one measurement parameter using the helpers at the bottom of _PARAMETERS.
4.  If the type uses an option parameter (e.g. severity, grade), add it via _severity_param() /
    _option_param() and list its choices in _PARAMETER_OPTIONS via _severity_options() /
    _option_options().
5.  Run:  python -c "import app.work_catalog.seeds"
    — the import-time guard (_validate_catalog_seed) will catch any inconsistency immediately.

Naming conventions
------------------
Category IDs    : wc_{snake_code}                   e.g. wc_roofing
Work type IDs   : wt_{snake_code}                   e.g. wt_roof_repair
Parameter IDs   : wtp_{wt_snake}_{param_snake}      e.g. wtp_roof_repair_area
Option IDs      : wtpo_{wt_snake}_{param_snake}_{code}  e.g. wtpo_roof_repair_sev_minor
"""

from __future__ import annotations

from typing import Any

from app.work_catalog.domain import validate_parameter_definition
from app.work_catalog.parameter_seed_data import (
    WORK_TYPE_PARAMETER_SCHEMAS,
    build_parameter_catalog,
)


# ---------------------------------------------------------------------------
# Analysis profiles — global AI execution contracts
# ---------------------------------------------------------------------------

_ANALYSIS_PROFILES: list[dict[str, Any]] = [
    {
        "id": "ap_surface_damage_v1",
        "code": "surface-damage-v1",
        "name": "Surface Damage Detection",
        "provider_family": "vision",
        "task_type": "hybrid",
        "output_contract_version": 1,
        "confidence_threshold": 0.55,
        "max_detections_per_photo": 25,
        "profile_version": 1,
    },
    {
        "id": "ap_coating_scope_v1",
        "code": "coating-scope-v1",
        "name": "Coating Scope Analysis",
        "provider_family": "vision",
        "task_type": "measurement",
        "output_contract_version": 1,
        "confidence_threshold": 0.50,
        "max_detections_per_photo": 20,
        "profile_version": 1,
    },
]

# ---------------------------------------------------------------------------
# Catalog pricing profiles — global pricing strategy contracts
# ---------------------------------------------------------------------------

_CATALOG_PRICING_PROFILES: list[dict[str, Any]] = [
    {
        "id": "cpp_surface_repair_standard_v1",
        "code": "surface-repair-standard-v1",
        "name": "Surface Repair Standard",
        "pricing_strategy": "tenant_pricebook",
        "labor_rate_source": "tenant_default",
        "material_pricing_source": "tenant_pricebook",
        "default_margin_pct": 18,
        "default_markup_pct": 0,
        "profile_version": 1,
    },
    {
        "id": "cpp_coating_standard_v1",
        "code": "coating-standard-v1",
        "name": "Coating Standard",
        "pricing_strategy": "tenant_pricebook",
        "labor_rate_source": "tenant_default",
        "material_pricing_source": "tenant_pricebook",
        "default_margin_pct": 15,
        "default_markup_pct": 0,
        "profile_version": 1,
    },
]

# Short aliases for use inside _WORK_TYPES entries — avoids repetition.
_AP_DAMAGE = "ap_surface_damage_v1"
_AP_COATING = "ap_coating_scope_v1"
_CPP_REPAIR = "cpp_surface_repair_standard_v1"
_CPP_COATING = "cpp_coating_standard_v1"

# ---------------------------------------------------------------------------
# Work categories — stable global taxonomy
# ---------------------------------------------------------------------------

_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "wc_masonry_structural",
        "code": "masonry-structural",
        "slug": "masonry-structural",
        "name": "Masonry & Structural",
        "description": "Masonry, structural reinforcement, plastering, facade systems, and foundation work.",
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_floors_paving",
        "code": "floors-paving",
        "slug": "floors-paving",
        "name": "Floors & Paving",
        "description": "Floor laying, tiling, renovation, and indoor/outdoor paving work.",
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_roofing",
        "code": "roofing",
        "slug": "roofing",
        "name": "Roofing",
        "description": "Roof installation, repair, insulation, gutters, and roof inspection services.",
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_windows_doors",
        "code": "windows-doors",
        "slug": "windows-doors",
        "name": "Windows & Doors",
        "description": "Installation, replacement, and repair of windows and doors.",
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_electrical",
        "code": "electrical",
        "slug": "electrical",
        "name": "Electrical",
        "description": "Electrical wiring installation and repair work.",
        "sort_order": 50,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_plumbing",
        "code": "plumbing",
        "slug": "plumbing",
        "name": "Plumbing",
        "description": "Plumbing system installation and repair.",
        "sort_order": 60,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_heating",
        "code": "heating",
        "slug": "heating",
        "name": "Heating Systems",
        "description": "Heating system installation including boilers, radiators, and full system integration.",
        "sort_order": 70,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_finishing",
        "code": "finishing",
        "slug": "finishing",
        "name": "Interior Finishing",
        "description": "Interior finishing work including painting, drywalling, and ceiling installation.",
        "sort_order": 80,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_exterior",
        "code": "exterior",
        "slug": "exterior",
        "name": "Exterior Works",
        "description": "Outdoor and exterior construction: terraces, fences, driveways, and landscaping.",
        "sort_order": 90,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wc_inspection_service",
        "code": "inspection-service",
        "slug": "inspection-service",
        "name": "Inspection & Service",
        "description": "Site inspections, scheduled maintenance, post-construction cleaning, and emergency response.",
        "sort_order": 100,
        "is_active": True,
        "catalog_version": 1,
    },
]

# ---------------------------------------------------------------------------
# Work types
# ---------------------------------------------------------------------------

_WORK_TYPES: list[dict[str, Any]] = [

    # ── masonry-structural ──────────────────────────────────────────────────
    {
        "id": "wt_chimney_renovation",
        "category_id": "wc_masonry_structural",
        "code": "chimney-renovation",
        "slug": "chimney-renovation",
        "name": "Chimney Renovation",
        "description": "Restoration, repointing, and structural repair of existing chimneys.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_chimney_new_build",
        "category_id": "wc_masonry_structural",
        "code": "chimney-new-build",
        "slug": "chimney-new-build",
        "name": "Chimney New Build",
        "description": "Construction of a new chimney from foundation to stack.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_wall_construction",
        "category_id": "wc_masonry_structural",
        "code": "wall-construction",
        "slug": "wall-construction",
        "name": "Wall Construction",
        "description": "New masonry wall construction including block, brick, or concrete work.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_wall_demolition",
        "category_id": "wc_masonry_structural",
        "code": "wall-demolition",
        "slug": "wall-demolition",
        "name": "Wall Demolition",
        "description": "Controlled demolition of interior or exterior walls.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_plastering",
        "category_id": "wc_masonry_structural",
        "code": "plastering",
        "slug": "plastering",
        "name": "Plastering",
        "description": "Application of plaster to interior or exterior wall and ceiling surfaces.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_COATING,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 50,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_facade_installation",
        "category_id": "wc_masonry_structural",
        "code": "facade-installation",
        "slug": "facade-installation",
        "name": "Facade Installation",
        "description": "Full facade cladding, ETICS system, or rainscreen installation.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_COATING,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 60,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_insulation_installation",
        "category_id": "wc_masonry_structural",
        "code": "insulation-installation",
        "slug": "insulation-installation",
        "name": "Insulation Installation",
        "description": "Thermal or acoustic insulation installation on walls, roofs, or floors.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 70,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_foundation_work",
        "category_id": "wc_masonry_structural",
        "code": "foundation-work",
        "slug": "foundation-work",
        "name": "Foundation Work",
        "description": "Foundation excavation, reinforcement, and concrete pour.",
        "default_unit": "m3",
        "measurement_kind": "volume",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 80,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── floors-paving ───────────────────────────────────────────────────────
    {
        "id": "wt_pedestal_paving",
        "category_id": "wc_floors_paving",
        "code": "pedestal-paving",
        "slug": "pedestal-paving",
        "name": "Pedestal Paving",
        "description": "Raised pedestal paving system installation for terraces or roof decks.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_tile_installation",
        "category_id": "wc_floors_paving",
        "code": "tile-installation",
        "slug": "tile-installation",
        "name": "Tile Installation",
        "description": "Ceramic, stone, or porcelain tile laying on floors or walls.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_floor_renovation",
        "category_id": "wc_floors_paving",
        "code": "floor-renovation",
        "slug": "floor-renovation",
        "name": "Floor Renovation",
        "description": "Repair or renovation of existing floor surfaces.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_vinyl_floor_installation",
        "category_id": "wc_floors_paving",
        "code": "vinyl-floor-installation",
        "slug": "vinyl-floor-installation",
        "name": "Vinyl Floor Installation",
        "description": "LVT / vinyl click or glue-down floor installation.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_wood_floor_installation",
        "category_id": "wc_floors_paving",
        "code": "wood-floor-installation",
        "slug": "wood-floor-installation",
        "name": "Wood Floor Installation",
        "description": "Solid hardwood or engineered wood floor installation and finishing.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 50,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_concrete_floor",
        "category_id": "wc_floors_paving",
        "code": "concrete-floor",
        "slug": "concrete-floor",
        "name": "Concrete Floor",
        "description": "Screeding, levelling, or polished concrete floor work.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 60,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── roofing ─────────────────────────────────────────────────────────────
    {
        "id": "wt_roof_repair",
        "category_id": "wc_roofing",
        "code": "roof-repair",
        "slug": "roof-repair",
        "name": "Roof Repair",
        "description": "Localised or full-area roof membrane, tile, or flashing repair.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_roof_installation",
        "category_id": "wc_roofing",
        "code": "roof-installation",
        "slug": "roof-installation",
        "name": "Roof Installation",
        "description": "Complete new roof structure including battens, membrane, and covering.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_roof_inspection",
        "category_id": "wc_roofing",
        "code": "roof-inspection",
        "slug": "roof-inspection",
        "name": "Roof Inspection",
        "description": "Technical inspection of roof condition with detailed condition report.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_gutter_installation",
        "category_id": "wc_roofing",
        "code": "gutter-installation",
        "slug": "gutter-installation",
        "name": "Gutter Installation",
        "description": "New rainwater gutter and downpipe system installation.",
        "default_unit": "m",
        "measurement_kind": "length",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_gutter_repair",
        "category_id": "wc_roofing",
        "code": "gutter-repair",
        "slug": "gutter-repair",
        "name": "Gutter Repair",
        "description": "Repair, resealing, or partial replacement of gutter sections.",
        "default_unit": "m",
        "measurement_kind": "length",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 50,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_roof_insulation",
        "category_id": "wc_roofing",
        "code": "roof-insulation",
        "slug": "roof-insulation",
        "name": "Roof Insulation",
        "description": "Thermal insulation installation on flat or pitched roofs.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 60,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── windows-doors ───────────────────────────────────────────────────────
    {
        "id": "wt_window_installation",
        "category_id": "wc_windows_doors",
        "code": "window-installation",
        "slug": "window-installation",
        "name": "Window Installation",
        "description": "Installation of new windows in prepared openings.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_window_replacement",
        "category_id": "wc_windows_doors",
        "code": "window-replacement",
        "slug": "window-replacement",
        "name": "Window Replacement",
        "description": "Removal of existing windows and installation of new units.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_door_installation",
        "category_id": "wc_windows_doors",
        "code": "door-installation",
        "slug": "door-installation",
        "name": "Door Installation",
        "description": "Installation of interior or exterior doors with frames.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_door_repair",
        "category_id": "wc_windows_doors",
        "code": "door-repair",
        "slug": "door-repair",
        "name": "Door Repair",
        "description": "Repair or adjustment of door frames, hinges, locks, or panels.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── electrical ──────────────────────────────────────────────────────────
    {
        "id": "wt_electrical_installation",
        "category_id": "wc_electrical",
        "code": "electrical-installation",
        "slug": "electrical-installation",
        "name": "Electrical Installation",
        "description": "Full or partial electrical system installation including wiring, panels, and outlets.",
        "default_unit": "set",
        "measurement_kind": "fixed",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_electrical_repair",
        "category_id": "wc_electrical",
        "code": "electrical-repair",
        "slug": "electrical-repair",
        "name": "Electrical Repair",
        "description": "Localised electrical fault diagnosis and repair.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── plumbing ────────────────────────────────────────────────────────────
    {
        "id": "wt_plumbing_installation",
        "category_id": "wc_plumbing",
        "code": "plumbing-installation",
        "slug": "plumbing-installation",
        "name": "Plumbing Installation",
        "description": "Full or partial plumbing system installation including pipework and fixtures.",
        "default_unit": "set",
        "measurement_kind": "fixed",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_plumbing_repair",
        "category_id": "wc_plumbing",
        "code": "plumbing-repair",
        "slug": "plumbing-repair",
        "name": "Plumbing Repair",
        "description": "Fault diagnosis and repair of plumbing leaks, joints, or fixtures.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── heating ─────────────────────────────────────────────────────────────
    {
        "id": "wt_heating_installation",
        "category_id": "wc_heating",
        "code": "heating-installation",
        "slug": "heating-installation",
        "name": "Heating System Installation",
        "description": "Full central heating system installation including pipework and controls.",
        "default_unit": "set",
        "measurement_kind": "fixed",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_boiler_installation",
        "category_id": "wc_heating",
        "code": "boiler-installation",
        "slug": "boiler-installation",
        "name": "Boiler Installation",
        "description": "Supply and installation of gas, oil, or heat-pump boiler unit.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_radiator_installation",
        "category_id": "wc_heating",
        "code": "radiator-installation",
        "slug": "radiator-installation",
        "name": "Radiator Installation",
        "description": "Installation or replacement of radiator units including valve fittings.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── finishing ───────────────────────────────────────────────────────────
    {
        "id": "wt_painting",
        "category_id": "wc_finishing",
        "code": "painting",
        "slug": "painting",
        "name": "Painting",
        "description": "Interior or exterior surface painting with primer and finish coats.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_COATING,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_interior_finishing",
        "category_id": "wc_finishing",
        "code": "interior-finishing",
        "slug": "interior-finishing",
        "name": "Interior Finishing",
        "description": "Complete interior finishing package covering surfaces, skirting, and joints.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": _AP_COATING,
        "default_catalog_pricing_profile_id": _CPP_COATING,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_drywall_installation",
        "category_id": "wc_finishing",
        "code": "drywall-installation",
        "slug": "drywall-installation",
        "name": "Drywall Installation",
        "description": "Stud wall construction and plasterboard lining.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_ceiling_installation",
        "category_id": "wc_finishing",
        "code": "ceiling-installation",
        "slug": "ceiling-installation",
        "name": "Ceiling Installation",
        "description": "Suspended or direct-fixed ceiling installation.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── exterior ────────────────────────────────────────────────────────────
    {
        "id": "wt_terrace_construction",
        "category_id": "wc_exterior",
        "code": "terrace-construction",
        "slug": "terrace-construction",
        "name": "Terrace Construction",
        "description": "New terrace structure including substrate, drainage, and surface layer.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_fence_installation",
        "category_id": "wc_exterior",
        "code": "fence-installation",
        "slug": "fence-installation",
        "name": "Fence Installation",
        "description": "Supply and installation of fencing panels, posts, and gates.",
        "default_unit": "m",
        "measurement_kind": "length",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_driveway_paving",
        "category_id": "wc_exterior",
        "code": "driveway-paving",
        "slug": "driveway-paving",
        "name": "Driveway Paving",
        "description": "Driveway or parking area paving with concrete blocks, asphalt, or resin.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_garden_landscaping",
        "category_id": "wc_exterior",
        "code": "garden-landscaping",
        "slug": "garden-landscaping",
        "name": "Garden Landscaping",
        "description": "Garden design, grading, planting, and hard landscaping features.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },

    # ── inspection-service ──────────────────────────────────────────────────
    {
        "id": "wt_inspection",
        "category_id": "wc_inspection_service",
        "code": "inspection",
        "slug": "inspection",
        "name": "Inspection",
        "description": "Structured on-site condition inspection with written report.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 10,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_maintenance",
        "category_id": "wc_inspection_service",
        "code": "maintenance",
        "slug": "maintenance",
        "name": "Maintenance",
        "description": "Scheduled preventive maintenance visit for building systems or surfaces.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 20,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_cleaning_after_construction",
        "category_id": "wc_inspection_service",
        "code": "cleaning-after-construction",
        "slug": "cleaning-after-construction",
        "name": "Post-Construction Cleaning",
        "description": "Deep cleaning of surfaces and spaces after construction works.",
        "default_unit": "m2",
        "measurement_kind": "area",
        "state": "active",
        "default_analysis_profile_id": None,
        "default_catalog_pricing_profile_id": None,
        "sort_order": 30,
        "is_active": True,
        "catalog_version": 1,
    },
    {
        "id": "wt_emergency_repair",
        "category_id": "wc_inspection_service",
        "code": "emergency-repair",
        "slug": "emergency-repair",
        "name": "Emergency Repair",
        "description": "Urgent on-call intervention for acute structural or systems failure.",
        "default_unit": "pcs",
        "measurement_kind": "count",
        "state": "active",
        "default_analysis_profile_id": _AP_DAMAGE,
        "default_catalog_pricing_profile_id": _CPP_REPAIR,
        "sort_order": 40,
        "is_active": True,
        "catalog_version": 1,
    },
]

# ---------------------------------------------------------------------------
# Legacy thin parameter helpers retained temporarily for local compatibility.
# Canonical source-of-truth parameter schema is generated below via build_parameter_catalog().
# ---------------------------------------------------------------------------

def _area_param(wt_id: str, sort: int = 10) -> dict[str, Any]:
    """Primary area measurement parameter (m²) for area-based work types."""
    return {
        "id": f"wtp_{wt_id}_area",
        "work_type_id": f"wt_{wt_id}",
        "code": "work-area-sqm",
        "slug": "work-area-sqm",
        "name": "Work Area",
        "description": "Measured work surface area in square metres.",
        "data_type": "number",
        "unit": "m2",
        "is_required": True,
        "sort_order": sort,
        "default_number_value": None,
    }


def _count_param(wt_id: str, sort: int = 10) -> dict[str, Any]:
    """Primary quantity measurement parameter (pcs) for count-based work types."""
    return {
        "id": f"wtp_{wt_id}_quantity",
        "work_type_id": f"wt_{wt_id}",
        "code": "quantity",
        "slug": "quantity",
        "name": "Quantity",
        "description": "Number of units to be executed.",
        "data_type": "number",
        "unit": "pcs",
        "is_required": True,
        "sort_order": sort,
        "default_number_value": None,
    }


def _length_param(wt_id: str, sort: int = 10) -> dict[str, Any]:
    """Primary length measurement parameter (m) for length-based work types."""
    return {
        "id": f"wtp_{wt_id}_length",
        "work_type_id": f"wt_{wt_id}",
        "code": "length-m",
        "slug": "length-m",
        "name": "Length",
        "description": "Total length of work in metres.",
        "data_type": "number",
        "unit": "m",
        "is_required": True,
        "sort_order": sort,
        "default_number_value": None,
    }


def _volume_param(wt_id: str, sort: int = 10) -> dict[str, Any]:
    """Primary volume measurement parameter (m³) for volume-based work types."""
    return {
        "id": f"wtp_{wt_id}_volume",
        "work_type_id": f"wt_{wt_id}",
        "code": "volume-m3",
        "slug": "volume-m3",
        "name": "Volume",
        "description": "Total work volume in cubic metres.",
        "data_type": "number",
        "unit": "m3",
        "is_required": True,
        "sort_order": sort,
        "default_number_value": None,
    }


def _scope_param(wt_id: str, sort: int = 10) -> dict[str, Any]:
    """Primary scope description parameter for fixed/set-rate work types."""
    return {
        "id": f"wtp_{wt_id}_scope",
        "work_type_id": f"wt_{wt_id}",
        "code": "scope-description",
        "slug": "scope-description",
        "name": "Scope Description",
        "description": "Brief description of the work scope for this engagement.",
        "data_type": "text",
        "unit": None,
        "is_required": True,
        "sort_order": sort,
        "default_text_value": None,
    }


def _severity_param(wt_id: str, sort: int = 20) -> dict[str, Any]:
    """Severity classification option parameter for repair and renovation work types."""
    return {
        "id": f"wtp_{wt_id}_severity",
        "work_type_id": f"wt_{wt_id}",
        "code": "severity-band",
        "slug": "severity-band",
        "name": "Severity Band",
        "description": "Operational severity classification for scoping and pricing.",
        "data_type": "option",
        "unit": None,
        "is_required": True,
        "sort_order": sort,
        "default_option_code": None,
    }


def _inspection_type_param(wt_id: str, sort: int = 20) -> dict[str, Any]:
    """Inspection type classification option parameter."""
    return {
        "id": f"wtp_{wt_id}_inspection_type",
        "work_type_id": f"wt_{wt_id}",
        "code": "inspection-type",
        "slug": "inspection-type",
        "name": "Inspection Type",
        "description": "Priority classification for the inspection visit.",
        "data_type": "option",
        "unit": None,
        "is_required": True,
        "sort_order": sort,
        "default_option_code": "routine",
    }


# ---------------------------------------------------------------------------
# Work type parameters
# ---------------------------------------------------------------------------

_PARAMETERS: list[dict[str, Any]] = [

    # masonry-structural
    _area_param("chimney_renovation"),
    _severity_param("chimney_renovation"),
    _count_param("chimney_new_build"),
    _area_param("wall_construction"),
    _area_param("wall_demolition"),
    _severity_param("wall_demolition"),
    _area_param("plastering"),
    _area_param("facade_installation"),
    _area_param("insulation_installation"),
    _volume_param("foundation_work"),

    # floors-paving
    _area_param("pedestal_paving"),
    _area_param("tile_installation"),
    _area_param("floor_renovation"),
    _severity_param("floor_renovation"),
    _area_param("vinyl_floor_installation"),
    _area_param("wood_floor_installation"),
    _area_param("concrete_floor"),

    # roofing
    _area_param("roof_repair"),
    _severity_param("roof_repair"),
    _area_param("roof_installation"),
    _count_param("roof_inspection"),
    _length_param("gutter_installation"),
    _length_param("gutter_repair"),
    _severity_param("gutter_repair"),
    _area_param("roof_insulation"),

    # windows-doors
    _count_param("window_installation"),
    _count_param("window_replacement"),
    _severity_param("window_replacement"),
    _count_param("door_installation"),
    _count_param("door_repair"),
    _severity_param("door_repair"),

    # electrical
    _scope_param("electrical_installation"),
    _count_param("electrical_repair"),
    _severity_param("electrical_repair"),

    # plumbing
    _scope_param("plumbing_installation"),
    _count_param("plumbing_repair"),
    _severity_param("plumbing_repair"),

    # heating
    _scope_param("heating_installation"),
    _count_param("boiler_installation"),
    _count_param("radiator_installation"),

    # finishing
    _area_param("painting"),
    _area_param("interior_finishing"),
    _area_param("drywall_installation"),
    _area_param("ceiling_installation"),

    # exterior
    _area_param("terrace_construction"),
    _length_param("fence_installation"),
    _area_param("driveway_paving"),
    _area_param("garden_landscaping"),

    # inspection-service
    _count_param("inspection"),
    _inspection_type_param("inspection"),
    _count_param("maintenance"),
    _severity_param("maintenance"),
    _area_param("cleaning_after_construction"),
    _count_param("emergency_repair"),
    _severity_param("emergency_repair"),
]

# ---------------------------------------------------------------------------
# Option helpers — generate option rows tied to a specific parameter ID.
# ---------------------------------------------------------------------------

def _severity_options(wt_id: str) -> list[dict[str, Any]]:
    """Three-tier severity options for wtp_{wt_id}_severity."""
    param_id = f"wtp_{wt_id}_severity"
    return [
        {"id": f"wtpo_{wt_id}_sev_minor",    "work_type_parameter_id": param_id, "code": "minor",    "label": "Minor",    "sort_order": 10, "is_active": True},
        {"id": f"wtpo_{wt_id}_sev_moderate", "work_type_parameter_id": param_id, "code": "moderate", "label": "Moderate", "sort_order": 20, "is_active": True},
        {"id": f"wtpo_{wt_id}_sev_major",    "work_type_parameter_id": param_id, "code": "major",    "label": "Major",    "sort_order": 30, "is_active": True},
    ]


def _inspection_type_options(wt_id: str) -> list[dict[str, Any]]:
    """Three-tier inspection type options for wtp_{wt_id}_inspection_type."""
    param_id = f"wtp_{wt_id}_inspection_type"
    return [
        {"id": f"wtpo_{wt_id}_itype_routine",   "work_type_parameter_id": param_id, "code": "routine",   "label": "Routine",   "sort_order": 10, "is_active": True},
        {"id": f"wtpo_{wt_id}_itype_priority",  "work_type_parameter_id": param_id, "code": "priority",  "label": "Priority",  "sort_order": 20, "is_active": True},
        {"id": f"wtpo_{wt_id}_itype_emergency", "work_type_parameter_id": param_id, "code": "emergency", "label": "Emergency", "sort_order": 30, "is_active": True},
    ]


# ---------------------------------------------------------------------------
# Work type parameter options
# ---------------------------------------------------------------------------

_PARAMETER_OPTIONS: list[dict[str, Any]] = [
    # masonry-structural severity options
    *_severity_options("chimney_renovation"),
    *_severity_options("wall_demolition"),

    # floors-paving severity options
    *_severity_options("floor_renovation"),

    # roofing severity options
    *_severity_options("roof_repair"),
    *_severity_options("gutter_repair"),

    # windows-doors severity options
    *_severity_options("window_replacement"),
    *_severity_options("door_repair"),

    # electrical severity options
    *_severity_options("electrical_repair"),

    # plumbing severity options
    *_severity_options("plumbing_repair"),

    # inspection-service
    *_inspection_type_options("inspection"),
    *_severity_options("maintenance"),
    *_severity_options("emergency_repair"),
]

# Canonical parametric schema replaces the legacy thin helper seed above.
_PARAMETERS, _PARAMETER_OPTIONS = build_parameter_catalog()

# ---------------------------------------------------------------------------
# Import-time catalog integrity guard
# ---------------------------------------------------------------------------

def _validate_catalog_seed() -> None:
    """Validate internal consistency of the catalog seed at import time.

    Catches:
    - duplicate category codes or IDs,
    - duplicate work type codes or IDs,
    - work types referencing unknown category / analysis-profile / pricing-profile IDs,
    - duplicate (work_type_id, code) pairs in parameters,
    - parameters referencing unknown work type IDs,
    - duplicate parameter IDs,
    - duplicate option IDs,
    - options referencing unknown parameter IDs.

    Raises AssertionError with a descriptive message on any violation.
    """
    category_ids: set[str] = set()
    category_codes: list[str] = []
    for c in _CATEGORIES:
        if c["id"] in category_ids:
            raise AssertionError(f"Duplicate category id: {c['id']!r}")
        category_ids.add(c["id"])
        category_codes.append(c["code"])
    _dup_codes = [code for code in category_codes if category_codes.count(code) > 1]
    if _dup_codes:
        raise AssertionError(f"Duplicate category codes: {sorted(set(_dup_codes))}")

    analysis_profile_ids = {p["id"] for p in _ANALYSIS_PROFILES}
    pricing_profile_ids = {p["id"] for p in _CATALOG_PRICING_PROFILES}

    work_type_ids: set[str] = set()
    work_type_codes: list[str] = []
    for wt in _WORK_TYPES:
        if wt["id"] in work_type_ids:
            raise AssertionError(f"Duplicate work type id: {wt['id']!r}")
        work_type_ids.add(wt["id"])
        work_type_codes.append(wt["code"])
        if wt["category_id"] not in category_ids:
            raise AssertionError(
                f"Work type {wt['code']!r} references unknown category_id {wt['category_id']!r}"
            )
        ap = wt.get("default_analysis_profile_id")
        if ap is not None and ap not in analysis_profile_ids:
            raise AssertionError(
                f"Work type {wt['code']!r} references unknown analysis_profile_id {ap!r}"
            )
        cpp = wt.get("default_catalog_pricing_profile_id")
        if cpp is not None and cpp not in pricing_profile_ids:
            raise AssertionError(
                f"Work type {wt['code']!r} references unknown pricing_profile_id {cpp!r}"
            )
    _dup_wt_codes = [code for code in work_type_codes if work_type_codes.count(code) > 1]
    if _dup_wt_codes:
        raise AssertionError(f"Duplicate work type codes: {sorted(set(_dup_wt_codes))}")

    param_ids: set[str] = set()
    param_keys: list[tuple[str, str]] = []
    section_coverage: dict[str, set[str]] = {}
    option_codes_by_parameter_id: dict[str, set[str]] = {}

    schema_work_type_ids = {f"wt_{wt_id}" for wt_id in WORK_TYPE_PARAMETER_SCHEMAS}
    if schema_work_type_ids != work_type_ids:
        missing = sorted(work_type_ids - schema_work_type_ids)
        extra = sorted(schema_work_type_ids - work_type_ids)
        raise AssertionError(
            f"Parameter schema coverage mismatch. Missing={missing}, extra={extra}"
        )

    for p in _PARAMETERS:
        if p["id"] in param_ids:
            raise AssertionError(f"Duplicate parameter id: {p['id']!r}")
        param_ids.add(p["id"])
        key = (p["work_type_id"], p["code"])
        if key in param_keys:
            raise AssertionError(
                f"Duplicate (work_type_id, code) in parameters: {p['work_type_id']!r} / {p['code']!r}"
            )
        param_keys.append(key)
        if p["work_type_id"] not in work_type_ids:
            raise AssertionError(
                f"Parameter {p['code']!r} references unknown work_type_id {p['work_type_id']!r}"
            )
        section_coverage.setdefault(p["work_type_id"], set()).add(p["section"])

    option_ids: set[str] = set()
    option_keys: set[tuple[str, str]] = set()
    for o in _PARAMETER_OPTIONS:
        if o["id"] in option_ids:
            raise AssertionError(f"Duplicate parameter option id: {o['id']!r}")
        option_ids.add(o["id"])
        if o["work_type_parameter_id"] not in param_ids:
            raise AssertionError(
                f"Option {o['code']!r} (id={o['id']!r}) references unknown "
                f"work_type_parameter_id {o['work_type_parameter_id']!r}"
            )
        option_key = (o["work_type_parameter_id"], o["code"])
        if option_key in option_keys:
            raise AssertionError(
                f"Duplicate option code for parameter {o['work_type_parameter_id']!r}: {o['code']!r}"
            )
        option_keys.add(option_key)
        option_codes_by_parameter_id.setdefault(o["work_type_parameter_id"], set()).add(o["code"])

    required_sections = {
        "dimensions",
        "materials",
        "condition_or_damage",
        "access_and_complexity",
        "quantity_scope",
        "optional_notes",
    }
    for work_type_id in sorted(work_type_ids):
        covered_sections = section_coverage.get(work_type_id, set())
        if covered_sections != required_sections:
            missing_sections = sorted(required_sections - covered_sections)
            raise AssertionError(
                f"Work type {work_type_id!r} does not cover all required parameter sections. "
                f"Missing: {missing_sections}"
            )

    for parameter in _PARAMETERS:
        validate_parameter_definition(
            parameter_code=parameter["code"],
            slug=parameter["slug"],
            label=parameter["name"],
            data_type=parameter["data_type"],
            unit=parameter.get("unit"),
            section=parameter.get("section"),
            min_number_value=parameter.get("min_number_value"),
            max_number_value=parameter.get("max_number_value"),
            vision_extractable=parameter.get("vision_extractable", False),
            manual_override_allowed=parameter.get("manual_override_allowed", True),
            default_text_value=parameter.get("default_text_value"),
            default_number_value=parameter.get("default_number_value"),
            default_boolean_value=parameter.get("default_boolean_value"),
            default_option_code=parameter.get("default_option_code"),
            option_codes=option_codes_by_parameter_id.get(parameter["id"], set()),
        )


# Run validation immediately on import — fail fast before any DB operation.
_validate_catalog_seed()

# ---------------------------------------------------------------------------
# Dev / test seed data — NOT part of the global catalog.
# These rows are dev-environment only and reference org_1 / price_default
# which are created by ensure_dev_seed() in bootstrap.py.
# ---------------------------------------------------------------------------

_DEV_TENANT_SETTINGS: list[dict[str, Any]] = [
    {
        "id": "twts_org_1_roof_repair",
        "organization_id": "org_1",
        "work_type_id": "wt_roof_repair",
        "status": "enabled",
        "custom_display_name": "Oprava strechy",
        "catalog_pricing_profile_id": "cpp_surface_repair_standard_v1",
        "tenant_pricing_profile_id": "price_default",
        "config_version": 1,
    },
    {
        "id": "twts_org_1_painting",
        "organization_id": "org_1",
        "work_type_id": "wt_painting",
        "status": "enabled",
        "custom_display_name": "Malovani",
        "catalog_pricing_profile_id": "cpp_coating_standard_v1",
        "tenant_pricing_profile_id": "price_default",
        "config_version": 1,
    },
]

_DEV_TENANT_PARAMETER_OVERRIDES: list[dict[str, Any]] = [
    {
        "id": "twpo_org_1_roof_repair_severity",
        "tenant_work_type_setting_id": "twts_org_1_roof_repair",
        "organization_id": "org_1",
        "work_type_id": "wt_roof_repair",
        "work_type_parameter_id": "wtp_roof_repair_severity",
        "override_status": "optional",
        "custom_display_name": "Zavaznost opravy strechy",
        "sort_order_override": 25,
        "config_version": 1,
    },
]

# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

#: Pure global catalog — safe to load in any environment.
CATALOG_SEED: dict[str, list[dict[str, Any]]] = {
    "categories": _CATEGORIES,
    "analysis_profiles": _ANALYSIS_PROFILES,
    "catalog_pricing_profiles": _CATALOG_PRICING_PROFILES,
    "work_types": _WORK_TYPES,
    "parameters": _PARAMETERS,
    "parameter_options": _PARAMETER_OPTIONS,
}

#: Combined seed used by bootstrap.py — includes dev/test tenant overrides.
GLOBAL_WORK_CATALOG_SEED: dict[str, list[dict[str, Any]]] = {
    **CATALOG_SEED,
    "tenant_settings": _DEV_TENANT_SETTINGS,
    "tenant_parameter_overrides": _DEV_TENANT_PARAMETER_OVERRIDES,
}
