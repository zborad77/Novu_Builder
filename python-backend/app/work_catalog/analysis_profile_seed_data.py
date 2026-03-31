from __future__ import annotations

from collections import defaultdict
from typing import Any


def _target(
    code: str,
    label: str,
    description: str,
    *,
    object_role: str,
    is_required: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "description": description,
        "object_role": object_role,
        "is_required": is_required,
    }


def _ignored(code: str, label: str, reason: str) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "reason": reason,
    }


_PROFILE_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "wt_chimney_renovation": {
        "code": "chimney-renovation-vision",
        "name": "Chimney Renovation Vision",
        "task_type": "hybrid",
        "scope_code": "chimney-damage-assessment",
        "scope_label": "Chimney Damage Assessment",
        "scope_description": "Assess masonry chimney stack condition, visible damage, and intervention scope.",
        "max_detections_per_photo": 18,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request one close-up of the stack crown and one wide roof-context photo when mortar joints are not readable.",
        "target_objects": [
            _target("chimney-stack", "Chimney Stack", "Primary chimney body, shaft, and visible faces.", object_role="primary", is_required=True),
            _target("chimney-crown", "Chimney Crown", "Top cap, flashing line, and rain cover area.", object_role="secondary"),
            _target("masonry-joint", "Masonry Joint", "Mortar joints, cracks, and repointing zones.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("tv-antenna", "TV Antenna", "Ignore mounted accessories that do not affect masonry scope."),
            _ignored("sky", "Sky", "Sky regions should not influence geometry or confidence."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_wall_demolition": {
        "code": "wall-demolition-vision",
        "name": "Wall Demolition Vision",
        "task_type": "hybrid",
        "scope_code": "wall-demolition-scope",
        "scope_label": "Wall Demolition Scope",
        "scope_description": "Measure wall area and classify demolition complexity from site imagery.",
        "max_detections_per_photo": 20,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Ask for a full-height wall photo with visible floor and ceiling edges when dimensions are incomplete.",
        "target_objects": [
            _target("wall-plane", "Wall Plane", "Primary wall plane to be demolished.", object_role="primary", is_required=True),
            _target("opening-edge", "Opening Edge", "Door and window openings influencing cut lines.", object_role="secondary"),
            _target("load-bearing-marker", "Load Bearing Marker", "Visible structural cues requiring manual confirmation.", object_role="context"),
        ],
        "ignored_objects": [
            _ignored("furniture", "Furniture", "Loose interior objects do not belong to demolition scope."),
            _ignored("temporary-storage", "Temporary Storage", "Stored materials should not be treated as target scope."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_plastering": {
        "code": "plastering-vision",
        "name": "Plastering Vision",
        "task_type": "measurement",
        "scope_code": "plaster-surface-coverage",
        "scope_label": "Plaster Surface Coverage",
        "scope_description": "Measure plasterable surfaces and classify substrate readiness for new plaster application.",
        "max_detections_per_photo": 24,
        "fallback_mode": "request_more_photos",
        "fallback_instructions": "Request one orthogonal surface photo per elevation when corners or full boundaries are missing.",
        "target_objects": [
            _target("plaster-surface", "Plaster Surface", "Wall or ceiling surface prepared for plaster application.", object_role="primary", is_required=True),
            _target("substrate-joint", "Substrate Joint", "Existing substrate transitions and joints affecting mesh or reinforcement.", object_role="secondary"),
            _target("corner-bead", "Corner Bead", "Visible edge and corner treatment points.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("window-glazing", "Window Glazing", "Glass and frames are excluded from plaster area."),
            _ignored("temporary-scaffold", "Temporary Scaffold", "Scaffolding only provides access context."),
        ],
        "minimum_photo_count": 3,
    },
    "wt_facade_installation": {
        "code": "facade-installation-vision",
        "name": "Facade Installation Vision",
        "task_type": "measurement",
        "scope_code": "facade-system-installation",
        "scope_label": "Facade System Installation",
        "scope_description": "Measure facade envelope surfaces and classify substrate conditions for new facade systems.",
        "max_detections_per_photo": 28,
        "fallback_mode": "request_more_photos",
        "fallback_instructions": "Request full-elevation photos with corner returns and base detail when envelope boundaries are incomplete.",
        "target_objects": [
            _target("facade-plane", "Facade Plane", "Primary elevation or facade envelope surface.", object_role="primary", is_required=True),
            _target("window-reveal", "Window Reveal", "Openings and reveals impacting facade detailing.", object_role="secondary"),
            _target("base-plinth", "Base Plinth", "Lower facade and plinth transition zone.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("vegetation", "Vegetation", "Trees and shrubs obscuring facade should be ignored."),
            _ignored("parked-vehicle", "Parked Vehicle", "Vehicles are excluded from facade scope."),
        ],
        "minimum_photo_count": 3,
    },
    "wt_floor_renovation": {
        "code": "floor-renovation-vision",
        "name": "Floor Renovation Vision",
        "task_type": "hybrid",
        "scope_code": "floor-damage-assessment",
        "scope_label": "Floor Damage Assessment",
        "scope_description": "Assess visible floor wear, damage severity, and repairable area for renovation scope.",
        "max_detections_per_photo": 16,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request one doorway-to-wall overview and one close-up of the dominant damaged zone when wear classification is uncertain.",
        "target_objects": [
            _target("floor-surface", "Floor Surface", "Primary floor area under renovation.", object_role="primary", is_required=True),
            _target("joint-line", "Joint Line", "Movement joints and cracked seams.", object_role="secondary"),
            _target("skirting-edge", "Skirting Edge", "Perimeter edges affecting local replacement or trimming.", object_role="context"),
        ],
        "ignored_objects": [
            _ignored("loose-rug", "Loose Rug", "Temporary coverings are not part of floor scope."),
            _ignored("portable-furniture", "Portable Furniture", "Movable furniture should not affect area estimation."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_roof_repair": {
        "code": "roof-repair-vision",
        "name": "Roof Repair Vision",
        "task_type": "hybrid",
        "scope_code": "roof-damage-assessment",
        "scope_label": "Roof Damage Assessment",
        "scope_description": "Assess roof covering damage, estimate intervention area, and classify access-sensitive repair scope.",
        "max_detections_per_photo": 25,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request one full-slope context photo and one close-up of the dominant defect whenever the covering type or break line is ambiguous.",
        "target_objects": [
            _target("roof-surface", "Roof Surface", "Primary roof plane or covering area.", object_role="primary", is_required=True),
            _target("flashing-line", "Flashing Line", "Chimney, wall, and valley flashing transitions.", object_role="secondary"),
            _target("roof-penetration", "Roof Penetration", "Vent, skylight, and service penetrations influencing repair detail.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("sky", "Sky", "Sky areas must not contribute to measured roof geometry."),
            _ignored("solar-panel", "Solar Panel", "Mounted solar equipment is not the repair target unless explicitly selected."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_gutter_repair": {
        "code": "gutter-repair-vision",
        "name": "Gutter Repair Vision",
        "task_type": "hybrid",
        "scope_code": "gutter-damage-assessment",
        "scope_label": "Gutter Damage Assessment",
        "scope_description": "Assess damaged gutter runs, leakage points, and repair length for rainwater systems.",
        "max_detections_per_photo": 14,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request an eaves-line overview and one detail of each leaking joint when run length or defect type is not visible.",
        "target_objects": [
            _target("gutter-run", "Gutter Run", "Primary gutter section or eaves run requiring intervention.", object_role="primary", is_required=True),
            _target("joint-connection", "Joint Connection", "Gutter joints, outlets, and brackets with visible defects.", object_role="secondary"),
            _target("downpipe-connection", "Downpipe Connection", "Outlet transitions influencing repair scope.", object_role="context"),
        ],
        "ignored_objects": [
            _ignored("fascia-shadow", "Fascia Shadow", "Strong shadows should not be treated as material defects."),
            _ignored("roof-covering", "Roof Covering", "Adjacent covering is context, not the direct repair target."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_window_replacement": {
        "code": "window-replacement-vision",
        "name": "Window Replacement Vision",
        "task_type": "hybrid",
        "scope_code": "window-replacement-survey",
        "scope_label": "Window Replacement Survey",
        "scope_description": "Classify existing window condition, opening geometry, and replacement complexity from site imagery.",
        "max_detections_per_photo": 12,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request one straight-on photo per opening and one side reveal when frame material or reveal depth is unclear.",
        "target_objects": [
            _target("window-opening", "Window Opening", "Primary opening including frame and reveal.", object_role="primary", is_required=True),
            _target("frame-joint", "Frame Joint", "Perimeter seal, joint, and reveal condition.", object_role="secondary"),
            _target("sill-line", "Sill Line", "Window sill and lower drainage edge.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("curtain-blind", "Curtain Or Blind", "Interior coverings do not affect replacement scope."),
            _ignored("reflective-glare", "Reflective Glare", "Strong reflections should not be treated as condition evidence."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_door_repair": {
        "code": "door-repair-vision",
        "name": "Door Repair Vision",
        "task_type": "hybrid",
        "scope_code": "door-repair-survey",
        "scope_label": "Door Repair Survey",
        "scope_description": "Assess door leaf, frame, and hardware condition for repair intervention scope.",
        "max_detections_per_photo": 12,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Request one full-height door photo and one close-up of the failing hinge, lock, or damaged panel area.",
        "target_objects": [
            _target("door-set", "Door Set", "Primary door leaf and frame assembly.", object_role="primary", is_required=True),
            _target("hardware-zone", "Hardware Zone", "Lock, hinge, and closer areas affecting repair type.", object_role="secondary"),
            _target("threshold-line", "Threshold Line", "Bottom threshold and floor transition.", object_role="context"),
        ],
        "ignored_objects": [
            _ignored("decorative-panel", "Decorative Panel", "Decorative trim should not be classified as structural damage."),
            _ignored("portable-signage", "Portable Signage", "Temporary signs are not repair targets."),
        ],
        "minimum_photo_count": 2,
    },
    "wt_painting": {
        "code": "painting-vision",
        "name": "Painting Vision",
        "task_type": "measurement",
        "scope_code": "painting-surface-coverage",
        "scope_label": "Painting Surface Coverage",
        "scope_description": "Measure paintable surfaces, detect substrate condition, and classify coating scope.",
        "max_detections_per_photo": 22,
        "fallback_mode": "request_more_photos",
        "fallback_instructions": "Request full-surface photos with corner context when the paintable boundary is cropped or partially obstructed.",
        "target_objects": [
            _target("paint-surface", "Paint Surface", "Primary interior or exterior painted surface.", object_role="primary", is_required=True),
            _target("coating-edge", "Coating Edge", "Surface boundaries, trim lines, and transitions.", object_role="secondary"),
            _target("defect-cluster", "Defect Cluster", "Peeling, blistering, or staining zones affecting preparation scope.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("furniture", "Furniture", "Movable furniture is excluded from paint area."),
            _ignored("glazing", "Glazing", "Glass panes are not paintable surface."),
        ],
        "minimum_photo_count": 3,
    },
    "wt_interior_finishing": {
        "code": "interior-finishing-vision",
        "name": "Interior Finishing Vision",
        "task_type": "measurement",
        "scope_code": "interior-finishing-coverage",
        "scope_label": "Interior Finishing Coverage",
        "scope_description": "Measure surfaces and classify finishing condition across interior rooms and detail zones.",
        "max_detections_per_photo": 24,
        "fallback_mode": "request_more_photos",
        "fallback_instructions": "Request one wide room shot and one detail photo of corners or joint transitions when finishing type is unclear.",
        "target_objects": [
            _target("room-surface", "Room Surface", "Primary wall or ceiling finishing surface.", object_role="primary", is_required=True),
            _target("joint-transition", "Joint Transition", "Room joints, corners, and trim transitions.", object_role="secondary"),
            _target("finish-detail", "Finish Detail", "Surface details affecting finishing complexity.", object_role="secondary"),
        ],
        "ignored_objects": [
            _ignored("temporary-lighting", "Temporary Lighting", "Temporary fittings are not finishing scope."),
            _ignored("portable-equipment", "Portable Equipment", "Tools and stored equipment do not affect surface classification."),
        ],
        "minimum_photo_count": 3,
    },
    "wt_emergency_repair": {
        "code": "emergency-repair-vision",
        "name": "Emergency Repair Vision",
        "task_type": "hybrid",
        "scope_code": "emergency-damage-triage",
        "scope_label": "Emergency Damage Triage",
        "scope_description": "Triage urgent damage, classify severity, and estimate immediate stabilization scope.",
        "max_detections_per_photo": 16,
        "fallback_mode": "manual_review",
        "fallback_instructions": "Escalate to manual review when the damaged system cannot be identified from at least one context and one close-up photo.",
        "target_objects": [
            _target("incident-zone", "Incident Zone", "Primary visible failure or damaged intervention zone.", object_role="primary", is_required=True),
            _target("safety-hazard", "Safety Hazard", "Secondary hazard context impacting urgency or access.", object_role="secondary"),
            _target("temporary-support", "Temporary Support", "Visible emergency support or shoring conditions.", object_role="context"),
        ],
        "ignored_objects": [
            _ignored("crowd", "Crowd", "People present on site are not analytical targets."),
            _ignored("response-vehicle", "Response Vehicle", "Emergency vehicles should not influence scope mapping."),
        ],
        "minimum_photo_count": 2,
    },
}


def _sort_key(parameter: dict[str, Any]) -> tuple[int, str]:
    return (int(parameter.get("sort_order", 100)), str(parameter["code"]))


def _primary_source_object_code(blueprint: dict[str, Any]) -> str:
    for target in blueprint["target_objects"]:
        if target["object_role"] == "primary":
            return target["code"]
    raise AssertionError("Analysis profile blueprint must define a primary target object.")


def _standard_attribute_mappings() -> list[tuple[str, str, str]]:
    return [
        ("analysis_result", "object_type", "object-type"),
        ("analysis_result", "surface_condition", "surface-condition"),
        ("analysis_result", "recommended_scope", "recommended-scope"),
        ("analysis_result", "estimated_quantity", "estimated-quantity"),
        ("analysis_result", "estimated_unit", "estimated-unit"),
        ("analysis_result", "estimated_area_sqm", "estimated-area-sqm"),
        ("analysis_result", "area_confidence", "area-confidence"),
        ("analysis_result", "mask_polygon", "mask-polygon"),
        ("analysis_result", "materials", "materials"),
        ("analysis_result", "workflow_steps", "workflow-steps"),
        ("analysis_result", "estimated_duration_days", "estimated-total-days"),
        ("analysis_result", "labor_hours_total", "labor-hours-total"),
    ]


def build_analysis_profile_catalog(
    *,
    work_types: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    work_types_by_id = {row["id"]: row for row in work_types}
    parameters_by_work_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for parameter in parameters:
        parameters_by_work_type[parameter["work_type_id"]].append(parameter)

    profiles: list[dict[str, Any]] = []
    target_objects: list[dict[str, Any]] = []
    ignored_objects: list[dict[str, Any]] = []
    extraction_rules: list[dict[str, Any]] = []
    validation_rules: list[dict[str, Any]] = []
    confidence_thresholds: list[dict[str, Any]] = []
    output_mappings: list[dict[str, Any]] = []

    for work_type_id, blueprint in _PROFILE_BLUEPRINTS.items():
        work_type = work_types_by_id.get(work_type_id)
        if work_type is None:
            raise AssertionError(f"Analysis profile blueprint references unknown work type '{work_type_id}'.")
        profile_id = f"ap_{work_type_id[3:]}_vision_v1"
        work_type_parameters = sorted(parameters_by_work_type.get(work_type_id, []), key=_sort_key)
        extractable_parameters = [row for row in work_type_parameters if row.get("vision_extractable")]
        if not extractable_parameters:
            raise AssertionError(
                f"Analysis profile blueprint '{work_type_id}' requires at least one vision-extractable parameter."
            )

        profiles.append(
            {
                "id": profile_id,
                "code": blueprint["code"],
                "name": blueprint["name"],
                "provider_family": "vision",
                "task_type": blueprint["task_type"],
                "output_contract_version": 2,
                "confidence_threshold": 0.60,
                "max_detections_per_photo": blueprint["max_detections_per_photo"],
                "is_active": True,
                "profile_version": 1,
                "status": "active",
                "scope_code": blueprint["scope_code"],
                "scope_label": blueprint["scope_label"],
                "scope_description": blueprint["scope_description"],
                "fallback_mode": blueprint["fallback_mode"],
                "fallback_instructions": blueprint["fallback_instructions"],
                "fallback_requires_manual_review": blueprint["fallback_mode"] == "manual_review",
            }
        )

        for sort_order, row in enumerate(blueprint["target_objects"], start=10):
            target_objects.append(
                {
                    "id": f"apto_{work_type_id[3:]}_{row['code'].replace('-', '_')}",
                    "analysis_profile_id": profile_id,
                    "code": row["code"],
                    "label": row["label"],
                    "description": row["description"],
                    "object_role": row["object_role"],
                    "is_required": row["is_required"],
                    "sort_order": sort_order,
                }
            )

        for sort_order, row in enumerate(blueprint["ignored_objects"], start=10):
            ignored_objects.append(
                {
                    "id": f"apio_{work_type_id[3:]}_{row['code'].replace('-', '_')}",
                    "analysis_profile_id": profile_id,
                    "code": row["code"],
                    "label": row["label"],
                    "reason": row["reason"],
                    "sort_order": sort_order,
                }
            )

        primary_object_code = _primary_source_object_code(blueprint)
        for sort_order, parameter in enumerate(extractable_parameters, start=10):
            extraction_rules.append(
                {
                    "id": f"aper_{work_type_id[3:]}_{parameter['code'].replace('-', '_')}",
                    "analysis_profile_id": profile_id,
                    "attribute_code": parameter["code"],
                    "label": parameter["name"],
                    "description": parameter.get("description"),
                    "data_type": parameter["data_type"],
                    "unit": parameter.get("unit"),
                    "target_parameter_code": parameter["code"],
                    "source_object_code": primary_object_code,
                    "is_required": parameter.get("is_required", False),
                    "manual_review_on_missing": not parameter.get("is_required", False),
                    "sort_order": sort_order,
                }
            )
            confidence_thresholds.append(
                {
                    "id": f"apct_{work_type_id[3:]}_{parameter['code'].replace('-', '_')}",
                    "analysis_profile_id": profile_id,
                    "attribute_code": parameter["code"],
                    "target_object_code": primary_object_code,
                    "min_confidence": 0.58 if parameter["data_type"] == "number" else 0.52,
                    "preferred_confidence": 0.78 if parameter["data_type"] == "number" else 0.68,
                    "action_below_threshold": "manual_review",
                    "sort_order": sort_order,
                }
            )
            output_mappings.append(
                {
                    "id": f"apom_{work_type_id[3:]}_{parameter['code'].replace('-', '_')}",
                    "analysis_profile_id": profile_id,
                    "code": f"project-work-item-{parameter['code']}",
                    "target_entity": "project_work_item_value",
                    "target_field": "value",
                    "source_attribute_code": parameter["code"],
                    "target_parameter_code": parameter["code"],
                    "is_required": parameter.get("is_required", False),
                    "sort_order": sort_order + 100,
                }
            )

            if parameter["data_type"] == "number":
                validation_rules.append(
                    {
                        "id": f"apvr_{work_type_id[3:]}_{parameter['code'].replace('-', '_')}_bounds",
                        "analysis_profile_id": profile_id,
                        "code": f"{parameter['code']}-bounds",
                        "rule_type": "numeric_range",
                        "severity": "blocking",
                        "target_attribute_code": parameter["code"],
                        "target_parameter_code": parameter["code"],
                        "min_number_value": parameter.get("min_number_value"),
                        "max_number_value": parameter.get("max_number_value"),
                        "message": f"Attribute '{parameter['code']}' must satisfy the parameter schema numeric bounds.",
                        "sort_order": sort_order + 200,
                    }
                )

            if parameter.get("is_required", False):
                validation_rules.append(
                    {
                        "id": f"apvr_{work_type_id[3:]}_{parameter['code'].replace('-', '_')}_required",
                        "analysis_profile_id": profile_id,
                        "code": f"{parameter['code']}-required",
                        "rule_type": "required_attribute",
                        "severity": "blocking",
                        "target_attribute_code": parameter["code"],
                        "target_parameter_code": parameter["code"],
                        "min_number_value": None,
                        "max_number_value": None,
                        "message": f"Required attribute '{parameter['code']}' was not extracted.",
                        "sort_order": sort_order + 300,
                    }
                )

        validation_rules.append(
            {
                "id": f"apvr_{work_type_id[3:]}_min_photos",
                "analysis_profile_id": profile_id,
                "code": "minimum-photo-count",
                "rule_type": "min_photos",
                "severity": "warning",
                "target_attribute_code": None,
                "target_parameter_code": None,
                "min_number_value": blueprint["minimum_photo_count"],
                "max_number_value": None,
                "message": f"At least {blueprint['minimum_photo_count']} photos are recommended for reliable analysis.",
                "sort_order": 5,
            }
        )

        for sort_order, (target_entity, target_field, source_attribute_code) in enumerate(_standard_attribute_mappings(), start=10):
            output_mappings.append(
                {
                    "id": f"apom_{work_type_id[3:]}_{target_entity}_{target_field}".replace("-", "_"),
                    "analysis_profile_id": profile_id,
                    "code": f"{target_entity}-{target_field}".replace("_", "-"),
                    "target_entity": target_entity,
                    "target_field": target_field,
                    "source_attribute_code": source_attribute_code,
                    "target_parameter_code": None,
                    "is_required": target_field in {"object_type", "recommended_scope"},
                    "sort_order": sort_order,
                }
            )

        output_mappings.append(
            {
                "id": f"apom_{work_type_id[3:]}_measured_quantity",
                "analysis_profile_id": profile_id,
                "code": "project-work-item-measured-quantity",
                "target_entity": "project_work_item",
                "target_field": "measured_quantity",
                "source_attribute_code": "estimated-quantity",
                "target_parameter_code": None,
                "is_required": False,
                "sort_order": 20,
            }
        )
        output_mappings.append(
            {
                "id": f"apom_{work_type_id[3:]}_measured_unit",
                "analysis_profile_id": profile_id,
                "code": "project-work-item-measured-unit",
                "target_entity": "project_work_item",
                "target_field": "measured_unit",
                "source_attribute_code": "estimated-unit",
                "target_parameter_code": None,
                "is_required": False,
                "sort_order": 21,
            }
        )

    return {
        "analysis_profiles": profiles,
        "analysis_profile_target_objects": target_objects,
        "analysis_profile_ignored_objects": ignored_objects,
        "analysis_profile_extraction_rules": extraction_rules,
        "analysis_profile_validation_rules": validation_rules,
        "analysis_profile_confidence_thresholds": confidence_thresholds,
        "analysis_profile_output_mappings": output_mappings,
    }
