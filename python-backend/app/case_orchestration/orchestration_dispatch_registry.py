from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DispatchType(str, Enum):
    INFRASTRUCTURE_ONLY = "infrastructure_only"
    ORCHESTRATION_OWNED = "orchestration_owned"


@dataclass(frozen=True)
class DispatchPoint:
    name: str
    dispatch_type: DispatchType
    description: str


DISPATCH_REGISTRY: dict[str, DispatchPoint] = {
    "worker.enqueue_job": DispatchPoint(
        name="worker.enqueue_job",
        dispatch_type=DispatchType.INFRASTRUCTURE_ONLY,
        description="Low-level queue transport used by reconciliation and transport infrastructure.",
    ),
    "analysis.enqueue": DispatchPoint(
        name="analysis.enqueue",
        dispatch_type=DispatchType.ORCHESTRATION_OWNED,
        description="Analysis job dispatch triggered by orchestration or its sanctioned adapters.",
    ),
    "quote.enqueue": DispatchPoint(
        name="quote.enqueue",
        dispatch_type=DispatchType.ORCHESTRATION_OWNED,
        description="Quote recalculation dispatch via command-driven orchestration path.",
    ),
    "export.enqueue": DispatchPoint(
        name="export.enqueue",
        dispatch_type=DispatchType.ORCHESTRATION_OWNED,
        description="Export generation dispatch via orchestration-owned flow.",
    ),
}


SANCTIONED_DISPATCH_CALL_SITES: dict[str, frozenset[str]] = {
    "python-backend/app/worker/queue.py": frozenset(),
    "python-backend/app/worker/heavy_queue.py": frozenset(),
    "python-backend/app/case_workflow/action_effects.py": frozenset(
        {"analysis.enqueue", "export.enqueue"}
    ),
    "python-backend/app/services/analysis_service.py": frozenset(
        {"analysis.enqueue", "quote.enqueue", "worker.enqueue_job"}
    ),
    "python-backend/app/services/export_service.py": frozenset({"export.enqueue"}),
    "python-backend/app/services/photo_service.py": frozenset({"worker.enqueue_job"}),
    "python-backend/app/worker/runner.py": frozenset({"worker.enqueue_job"}),
}


INFRASTRUCTURE_ONLY_DISPATCH_NAMES = frozenset(
    name
    for name, point in DISPATCH_REGISTRY.items()
    if point.dispatch_type == DispatchType.INFRASTRUCTURE_ONLY
)
ORCHESTRATION_OWNED_DISPATCH_NAMES = frozenset(
    name
    for name, point in DISPATCH_REGISTRY.items()
    if point.dispatch_type == DispatchType.ORCHESTRATION_OWNED
)
SANCTIONED_DISPATCH_NAMES = frozenset(DISPATCH_REGISTRY)
SANCTIONED_DISPATCH_PATHS = frozenset(SANCTIONED_DISPATCH_CALL_SITES)


def registered_dispatch_point(dispatch_name: str) -> DispatchPoint | None:
    return DISPATCH_REGISTRY.get(dispatch_name)


def allowed_dispatch_names_for_path(path: str) -> frozenset[str]:
    return SANCTIONED_DISPATCH_CALL_SITES.get(path, frozenset())
