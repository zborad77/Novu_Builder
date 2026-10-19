from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.work_catalog.seed_ids import (
    MAX_SEED_ID_LENGTH,
    assert_valid_seed_id_collection,
    build_analysis_profile_id,
    build_catalog_pricing_profile_id,
    build_seed_id,
    build_work_type_parameter_id,
    build_work_type_parameter_option_id,
)
from app.work_catalog.seeds import GLOBAL_WORK_CATALOG_SEED


def test_seed_id_helpers_preserve_stable_known_ids():
    assert build_work_type_parameter_id("roof_repair", "severity") == "wtp_roof_repair_severity"
    assert build_work_type_parameter_option_id("roof_repair", "severity", "minor") == "wtpo_roof_repair_severity_minor"
    assert build_analysis_profile_id("wt_roof_repair") == "ap_roof_repair_vision_v1"
    assert build_catalog_pricing_profile_id("roof-repair") == "cpp_roof_repair_pricing_v1"


def test_build_seed_id_is_deterministic_and_hashes_overflow():
    parts = (
        "roof_repair_with_a_very_long_work_type_identifier_that_keeps_going",
        "project_work_item_value",
        "estimated_quantity_with_extra_suffix_to_force_overflow",
    )
    seed_id = build_seed_id("apom", *parts)

    assert seed_id == build_seed_id("apom", *parts)
    assert len(seed_id) <= MAX_SEED_ID_LENGTH
    assert re.search(r"_[0-9a-f]{10}$", seed_id)

    other_seed_id = build_seed_id(
        "apom",
        parts[0],
        parts[1],
        "estimated_quantity_with_extra_suffix_to_force_overflow_v2",
    )
    assert other_seed_id != seed_id
    assert len(other_seed_id) <= MAX_SEED_ID_LENGTH


def test_build_seed_id_rejects_invalid_parts():
    with pytest.raises(AssertionError, match="lowercase ASCII letters, digits, underscores, or hyphens"):
        build_seed_id("ap", "roof repair")


def test_global_work_catalog_seed_ids_fit_contract_and_remain_unique():
    for key, rows in GLOBAL_WORK_CATALOG_SEED.items():
        assert_valid_seed_id_collection((row["id"] for row in rows), context=key)


def test_seed_builder_modules_do_not_inline_dynamic_seed_ids():
    repo_root = Path(__file__).resolve().parents[1]
    guarded_modules = (
        repo_root / "app" / "work_catalog" / "parameter_seed_data.py",
        repo_root / "app" / "work_catalog" / "analysis_profile_seed_data.py",
        repo_root / "app" / "work_catalog" / "pricing_profile_seed_data.py",
    )

    forbidden_patterns = (
        '"id": f',
        'profile_id = f"',
    )

    for path in guarded_modules:
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            assert pattern not in text, f"{path.name} must use app.work_catalog.seed_ids instead of inline seed ID building."
