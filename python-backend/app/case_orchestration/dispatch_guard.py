from __future__ import annotations

from app.case_orchestration.orchestration_dispatch_registry import (
    DISPATCH_REGISTRY,
    DispatchPoint,
)

STRICT_DISPATCH = True


def assert_dispatch_allowed(dispatch_name: str) -> DispatchPoint:
    dispatch_point = DISPATCH_REGISTRY.get(dispatch_name)
    if not STRICT_DISPATCH:
        if dispatch_point is None:
            raise RuntimeError(
                f"Dispatch {dispatch_name!r} is not registered even though strict mode is disabled."
            )
        return dispatch_point

    if dispatch_point is None:
        raise RuntimeError(
            f"Unauthorized dispatch: {dispatch_name!r}. "
            "Must be registered in DISPATCH_REGISTRY."
        )
    return dispatch_point
