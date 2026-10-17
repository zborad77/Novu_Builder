# Coding Standard

NOVU Builder code must be deterministic, explicit, and production ready.

## Core Rules

- Write deterministic code.
- Use typed interfaces.
- Raise explicit errors.
- Do not swallow broad exceptions.
- Do not duplicate business logic.
- Do not mutate hidden state.
- Preserve Route -> Service -> Repository -> ORM layering.
- Do not calculate pricing outside the Pricing Engine.
- Do not bypass validation.

## Error Handling

Critical failures must be visible and actionable. Broad exception handling must be scoped, logged, justified, and tested.

## Architecture Fit

Prefer existing abstractions, repositories, services, schemas, and domain helpers. Add new abstractions only when they remove real duplication or clarify ownership.

## Maintainability

Avoid dead code, unexplained TODOs, temporary hacks, and unrelated refactors. Keep changes small and reviewable.
