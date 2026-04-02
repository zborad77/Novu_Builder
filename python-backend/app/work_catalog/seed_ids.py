from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable


MAX_SEED_ID_LENGTH = 64
_HASH_SUFFIX_LENGTH = 10
_SEED_ID_RE = re.compile(r"^[a-z0-9_]+$")


def normalize_seed_id_part(part: str, *, field_name: str = "seed_id_part") -> str:
    normalized = part.replace("-", "_")
    if not normalized:
        raise AssertionError(f"{field_name} must not be empty.")
    if not _SEED_ID_RE.fullmatch(normalized):
        raise AssertionError(
            f"{field_name}={part!r} must use lowercase ASCII letters, digits, underscores, or hyphens."
        )
    return normalized


def validate_seed_id(seed_id: str, *, context: str = "seed_id") -> str:
    if not seed_id:
        raise AssertionError(f"{context} must not be empty.")
    if len(seed_id) > MAX_SEED_ID_LENGTH:
        raise AssertionError(
            f"{context}={seed_id!r} exceeds max length {MAX_SEED_ID_LENGTH}."
        )
    if not _SEED_ID_RE.fullmatch(seed_id):
        raise AssertionError(
            f"{context}={seed_id!r} must use lowercase ASCII letters, digits, or underscores."
        )
    return seed_id


def build_seed_id(prefix: str, *parts: str) -> str:
    normalized_prefix = normalize_seed_id_part(prefix, field_name="seed_id_prefix")
    normalized_parts = [
        normalize_seed_id_part(part, field_name=f"seed_id_part[{index}]")
        for index, part in enumerate(parts)
    ]
    raw_id = "_".join((normalized_prefix, *normalized_parts))
    if len(raw_id) <= MAX_SEED_ID_LENGTH:
        return validate_seed_id(raw_id)

    digest = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:_HASH_SUFFIX_LENGTH]
    head_length = MAX_SEED_ID_LENGTH - len(digest) - 1
    if head_length <= 0:
        raise AssertionError("Seed ID max length is too small for deterministic overflow protection.")
    return validate_seed_id(f"{raw_id[:head_length]}_{digest}")


def build_work_type_parameter_id(work_type_key: str, parameter_key: str) -> str:
    return build_seed_id("wtp", work_type_key, parameter_key)


def build_work_type_parameter_option_id(
    work_type_key: str,
    parameter_key: str,
    option_code: str,
) -> str:
    return build_seed_id("wtpo", work_type_key, parameter_key, option_code)


def build_analysis_profile_id(work_type_id_or_key: str) -> str:
    return build_seed_id("ap", _work_type_seed_key(work_type_id_or_key), "vision", "v1")


def build_analysis_profile_component_id(
    prefix: str,
    work_type_id_or_key: str,
    *parts: str,
) -> str:
    return build_seed_id(prefix, _work_type_seed_key(work_type_id_or_key), *parts)


def build_catalog_pricing_profile_id(work_type_code: str) -> str:
    return build_seed_id("cpp", work_type_code, "pricing", "v1")


def build_catalog_pricing_profile_component_id(
    prefix: str,
    work_type_code: str,
    *parts: str,
) -> str:
    return build_seed_id(prefix, work_type_code, *parts)


def assert_valid_seed_id_collection(ids: Iterable[str], *, context: str) -> None:
    seen: set[str] = set()
    for index, seed_id in enumerate(ids):
        validate_seed_id(seed_id, context=f"{context}[{index}]")
        if seed_id in seen:
            raise AssertionError(f"Duplicate {context} seed ID: {seed_id!r}")
        seen.add(seed_id)


def _work_type_seed_key(work_type_id_or_key: str) -> str:
    if work_type_id_or_key.startswith("wt_"):
        return normalize_seed_id_part(work_type_id_or_key[3:], field_name="work_type_key")
    return normalize_seed_id_part(work_type_id_or_key, field_name="work_type_key")
