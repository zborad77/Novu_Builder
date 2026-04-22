"""Incremental orchestration entry points.

This package hosts small, command-oriented building blocks that move the
runtime toward the target deterministic orchestration engine.
"""

from app.case_orchestration.dispatch_guard import STRICT_DISPATCH, assert_dispatch_allowed
from app.case_orchestration.orchestration_dispatch_registry import (
    DISPATCH_REGISTRY,
    INFRASTRUCTURE_ONLY_DISPATCH_NAMES,
    ORCHESTRATION_OWNED_DISPATCH_NAMES,
    SANCTIONED_DISPATCH_CALL_SITES,
    SANCTIONED_DISPATCH_NAMES,
    SANCTIONED_DISPATCH_PATHS,
    DispatchPoint,
    DispatchType,
)

__all__ = [
    "DISPATCH_REGISTRY",
    "DispatchPoint",
    "DispatchType",
    "INFRASTRUCTURE_ONLY_DISPATCH_NAMES",
    "ORCHESTRATION_OWNED_DISPATCH_NAMES",
    "SANCTIONED_DISPATCH_CALL_SITES",
    "SANCTIONED_DISPATCH_NAMES",
    "SANCTIONED_DISPATCH_PATHS",
    "STRICT_DISPATCH",
    "assert_dispatch_allowed",
]
