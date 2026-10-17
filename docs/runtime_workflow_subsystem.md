# Runtime Workflow Subsystem

## Purpose

`ProjectWorkItem` and `ProjectWorkItemValue` form the runtime execution layer of the work catalog core module.
They let one project carry many work items, each bound to a catalog work type, typed parameter values, operator confirmation state, and vision detection evidence.

## Runtime Data Model

- `ProjectWorkItem`
  Runtime aggregate for one resolved work type inside one project.
  Stores resolved catalog/profile snapshot fields, tenant context, pricing/profile references, and aggregate confirmation state.
- `ProjectWorkItemValue`
  Typed runtime value row.
  Binds to exactly one parameter definition:
  - global `work_type_parameter_id`, or
  - tenant `tenant_work_type_extra_parameter_id`.
- `VisionDetection`
  Append-friendly detection evidence row linked to project, work item, optional photo, optional analysis job, and resolved analysis profile snapshot.

## Source, Confidence, Confirmation

Runtime values now track:

- `source_type`
  `manual`, `vision`, `default`, `imported` with backward-compatible alias normalization for legacy `system` / `import`.
- `source_confidence`
  Optional confidence score, primarily for vision/import merges.
- `source_detection_id`
  Optional trace to the originating `VisionDetection`.
- `confirmation_status`
  `pending`, `confirmed`, `corrected`, `defaulted`.
- `confirmed_by_user_id`, `confirmed_at`
  Operator audit fields.
- `operator_note`
  Optional operator rationale.

Aggregate work item confirmation is derived from value rows:

- `pending`
  Only pending/defaulted values remain.
- `mixed`
  Combination of pending and operator-confirmed/corrected values.
- `confirmed`
  All active values are `confirmed`, `corrected`, or `defaulted`.

## Workflow Operations

- create work item
  Resolves tenant-effective schema, validates typed values, materializes defaults, snapshots effective catalog/profile state.
- fetch effective configuration
  Resolves the project-scoped effective configuration before runtime creation and returns explicit vision/pricing dependency surfaces for UI and orchestration.
- replace values
  Full typed replacement with required-parameter enforcement.
- update / merge values
  Partial upsert preserving existing values and applying deterministic source precedence.
- confirm values
  Operator can confirm a pending value or correct it into a manual value with audit metadata.
- fetch normalized detail
  Returns one normalized runtime aggregate with `workItem`, current `effectiveConfiguration`, and derived `workflow` hints ready for UI/operator/pricing consumers.

## Merge Rules

- manual input wins over non-manual sources,
- confirmed/corrected manual values are not overwritten by later vision input,
- imported values can replace default/vision/imported pending values,
- vision values can replace default values or weaker unconfirmed vision values when confidence improves.

## Hot Query Patterns

Most common read/write paths:

- `project_id + organization_id -> list work items`
- `project_id + project_work_item_id + organization_id -> work item detail`
- `project_id + organization_id + work_type_code -> effective configuration bootstrap`
- `project_work_item_id + confirmation_status -> operator review queue`
- `analysis_profile_id + resolved_work_type_code -> detection lookup`
- `catalog_pricing_profile_id + resolved_work_type_code -> pricing preparation`

Indexes support these paths directly on:

- `project_work_items`
- `project_work_item_values`
- `vision_detections`

Operational hardening on top of those indexes:

- project effective-configuration bootstrap is shared per tenant + work type and guarded by a project ownership existence check before cache hit reuse
- repeated effective/analyze/price resolution inside one workflow uses in-process memoization to avoid rebuilding the same ORM graph multiple times
- repository detail queries use `selectinload` graphs consistently so runtime detail and list endpoints do not degrade into N+1 behavior as value rows and detections grow

## Guards

- invalid parameter codes are rejected centrally before persistence,
- runtime value rows must bind to exactly one parameter definition source,
- cross-tenant and cross-project work item reads are tenant-scoped,
- project-scoped effective configuration validates project ownership before serving a cached tenant/work-type payload,
- detection references must belong to the same project and cannot point to another work item,
- typed value shape, bounds, and option membership stay enforced through the same catalog validation layer.
