"""Transition effect registry.

Two phases run around every committed status transition:

  before_commit — DB mutations atomic with the transition.
                  Runs inside the open session, before session.commit().
                  A raised exception rolls back the entire transaction.

  after_commit  — Network calls, queue enqueues, external notifications, and
                  other fire-and-forget effects that must not block the DB
                  commit. Failures are caught, logged, and swallowed — the
                  transition is already durable and must not be reversed.

Effects are registered against a concrete ``from_status -> to_status``
transition so they stay anchored to the state machine instead of being spread
across unrelated services.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Callable

import structlog

from app.case_workflow.transitions import can_transition

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.domain import Project

logger = structlog.get_logger(__name__)

EffectFn = Callable[["EffectContext"], Awaitable[None]]
TransitionKey = tuple[str, str]

_BEFORE_COMMIT: dict[TransitionKey, list[EffectFn]] = defaultdict(list)
_AFTER_COMMIT: dict[TransitionKey, list[EffectFn]] = defaultdict(list)


@dataclass(frozen=True)
class EffectContext:
    project: "Project"
    action: str
    from_status: str
    to_status: str
    actor_user_id: str | None
    actor_role: str
    organization_id: str | None
    is_superadmin_context: bool
    session: "AsyncSession"
    work_queue: "Redis | None" = None
    state: dict[str, object] = field(default_factory=dict)


def _normalize_transition_key(from_status: str, to_status: str) -> TransitionKey:
    normalized_from = from_status.strip()
    normalized_to = to_status.strip()
    if not can_transition(normalized_from, normalized_to):
        raise ValueError(
            f"Cannot register transition effect for unknown transition "
            f"{normalized_from!r} -> {normalized_to!r}."
        )
    return normalized_from, normalized_to


def before_transition(from_status: str, to_status: str) -> Callable[[EffectFn], EffectFn]:
    """Decorator: register *fn* as a before-commit effect for one transition."""
    key = _normalize_transition_key(from_status, to_status)

    def decorator(fn: EffectFn) -> EffectFn:
        _BEFORE_COMMIT[key].append(fn)
        return fn
    return decorator


def after_transition(from_status: str, to_status: str) -> Callable[[EffectFn], EffectFn]:
    """Decorator: register *fn* as an after-commit effect for one transition."""
    key = _normalize_transition_key(from_status, to_status)

    def decorator(fn: EffectFn) -> EffectFn:
        _AFTER_COMMIT[key].append(fn)
        return fn
    return decorator


async def run_before_commit(ctx: EffectContext) -> None:
    """Run all before-commit effects for one concrete transition."""
    key = (ctx.from_status, ctx.to_status)
    for fn in _BEFORE_COMMIT.get(key, []):
        await fn(ctx)


async def run_after_commit(ctx: EffectContext) -> None:
    """Run all after-commit effects for one concrete transition."""
    key = (ctx.from_status, ctx.to_status)
    for fn in _AFTER_COMMIT.get(key, []):
        try:
            await fn(ctx)
        except Exception:
            logger.exception(
                "transition.after_commit_effect_failed",
                action=ctx.action,
                from_status=ctx.from_status,
                to_status=ctx.to_status,
                project_id=ctx.project.id,
                effect=fn.__name__,
            )
