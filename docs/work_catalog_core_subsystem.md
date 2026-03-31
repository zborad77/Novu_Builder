# Work Catalog Core Subsystem

## Purpose

`work_catalog` is the source-of-truth subsystem for work classification and execution metadata in NOVU Builder.
It separates:

- global catalog definitions,
- tenant effective configuration,
- runtime project work items,
- vision detections,
- pricing/analysis profile resolution.

The subsystem is intentionally modeled as explicit relational entities instead of free-form JSON blobs so it can scale, evolve, and stay auditable.

## Module Structure

- `python-backend/app/work_catalog/domain.py`
  Centralized machine-code normalization, enum domains, and typed value validation.
- `python-backend/app/work_catalog/seeds.py`
  Canonical global catalog seed data for categories, work types, parameters, options, and baseline profiles.
- `python-backend/app/models/work_catalog.py`
  ORM source of truth for catalog, tenant, runtime, and detection entities.
- `python-backend/app/repositories/work_catalog_repository.py`
  Tenant-safe DB access and hot read query patterns.
- `python-backend/app/services/work_catalog_service.py`
  Effective resolution logic, runtime projection, typed value enforcement, and detection orchestration.
- `python-backend/app/services/tenant_work_type_resolution_service.py`
  Central tenant-effective resolver that merges global catalog, sparse tenant overrides, controlled tenant extra parameters, and effective analysis/pricing profile references.
- `docs/runtime_workflow_subsystem.md`
  Runtime data flow for project work items, typed value rows, merge/confirm semantics, and hot query patterns.
- `python-backend/app/schemas/work_catalog.py`
  Stable API and service contracts.
- `python-backend/app/api/routes/work_catalog.py`
  Tenant-scoped catalog and runtime endpoints with cache-aware read paths.
- `python-backend/alembic/versions/20260330_0028_create_work_catalog_core_subsystem.py`
  Explicit schema migration for the subsystem.

## Entity Model

### Global Catalog

- `WorkCategory`
  Stable global taxonomy root.
- `WorkType`
  Stable machine-readable work definition with default analysis/pricing profile references.
- `WorkTypeParameter`
  Explicit typed parameter schema per work type.
- `WorkTypeParameterOption`
  Explicit allowed options for option parameters.
- `AnalysisProfile`
  Global analysis execution contract and output versioning.
- `CatalogPricingProfile`
  Global versioned pricing contract with required inputs, base rules, adjustment rules, and labor/material assumptions. This is intentionally separate from existing tenant `PricingProfile` pricebooks.

### Tenant Effective Layer

- `TenantWorkTypeSetting`
  Per-tenant override record without duplicating global rows. Stores enablement, display override, resolved profile overrides, and tenant pricebook linkage.
- `TenantWorkTypeParameterOverride`
  Sparse per-tenant delta for parameter behavior. Supports required/optional/hidden transitions, display-name override, ordering override, and typed default override without cloning the global parameter schema.
- `TenantWorkTypeExtraParameter`
  Controlled tenant extension definition that augments a work type without mutating or copying the global parameter catalog.
- `TenantWorkTypeExtraParameterOption`
  Explicit enum option set for tenant extra option parameters.

### Runtime Project Layer

- `ProjectWorkItem`
  Runtime project entity created from effective work type resolution. Stores immutable snapshot fields needed for audit and long-term correctness, plus aggregate confirmation state.
- `ProjectWorkItemValue`
  Typed value rows bound to either global or tenant parameter definitions, with source tracking, confidence, confirmation status, and resolved parameter metadata snapshot.

### Vision Layer

- `VisionDetection`
  Detection/event log linked to project, work type, optional work item, optional analysis job, and optional photo reference.

### Pricing Layer

- `CatalogPricingProfileRequiredInput`
  Structured declaration of runtime inputs needed by pricing execution.
- `CatalogPricingProfileBaseRule`
  Explainable cost line rule for labor, material, or other cost buckets.
- `CatalogPricingProfileAdjustmentRule`
  Conditional surcharge / uplift / flat-charge rule without route-level hardcode.
- `CatalogPricingProfileLaborAssumption`
  Explicit productivity assumption per work type profile.
- `CatalogPricingProfileMaterialAssumption`
  Explicit material allowance assumption per work type profile.

## Boundaries

### Global

- owns catalog codes, slugs, parameters, options, and default analysis/pricing profiles
- does not store tenant-specific copies
- changes are versioned via `catalog_version` / `profile_version`

### Tenant

- stores only deltas from global definitions
- links a tenant to an existing global work type
- may override enablement, display name, analysis profile, catalog pricing profile, and tenant pricebook
- may add controlled tenant extra parameters using `tenant.*` codes
- avoids per-tenant catalog duplication

### Runtime

- stores resolved snapshot fields on `ProjectWorkItem` and `ProjectWorkItemValue`
- stores resolved analysis and pricing profile code/version snapshots on `ProjectWorkItem`
- remains historically correct even when the global catalog evolves later
- supports multiple items of the same work type per project via `item_sequence`

### Vision

- keeps raw detection facts separate from catalog and runtime projections
- allows future re-linking, rejection, or replay without mutating catalog definitions

## Scaling Design

- machine-readable `code` / `slug` values are globally unique and index-backed
- tenant overrides are sparse and delta-based, so 100k tenants do not require catalog row duplication
- runtime rows denormalize `organization_id`, resolved codes, and version fields for hot tenant/project lookups
- runtime values keep source/confidence/confirmation metadata in-row, so operator review and pricing prep do not require replaying external events
- project work items use compound indexes for `organization_id + project_id + status`
- project work items also expose `project_id + confirmation_status` for operator review queues
- vision detections use compound indexes for `organization_id + project_id + status`
- pricing profiles and their rule tables are indexed by `profile_id + sort_order` for predictable hot reads
- effective catalog reads are cacheable because the source of truth is stable and invalidation is explicit on tenant override writes
- tenant-effective resolution, analysis profile resolution, and pricing profile resolution now use in-process memoization inside a service instance to avoid repeated DB graph assembly during one workflow execution
- repository hot paths avoid duplicated eager loads for tenant settings versus parameter override / extra-parameter batch queries

## API Surfaces

### Global Catalog Reads

- `GET /api/v1/work-catalog/catalog/categories`
  Stable global category list with active and total work type counts.
- `GET /api/v1/work-catalog/catalog/work-types`
  Global work type list optimized for picker, mobile browse, and operator search views.
- `GET /api/v1/work-catalog/catalog/work-types/{workTypeCode}`
  Global work type detail with default analysis profile, default catalog pricing profile, parameter list, and parameter sections.
- `GET /api/v1/work-catalog/catalog/work-types/{workTypeCode}/parameters/{parameterCode}`
  Source-of-truth parameter schema detail including explicit analysis and pricing bindings.

### Tenant Effective Reads

- `GET /api/v1/work-catalog/work-types`
  Tenant-effective work type list for form bootstrap and tenant-aware catalog browse.
- `GET /api/v1/work-catalog/work-types/{workTypeCode}/effective`
  Effective tenant configuration for one work type.

### Runtime Workflow Reads And Writes

- `GET /api/v1/cases/{caseId}/work-types/{workTypeCode}/effective-configuration`
  Project-scoped effective configuration used before creating a work item. Returns effective work type plus workflow-ready vision/pricing dependency surfaces.
- `POST /api/v1/cases/{caseId}/work-items`
  Creates a runtime work item snapshot from the effective configuration.
- `PUT /api/v1/cases/{caseId}/work-items/{projectWorkItemId}/values`
  Full typed replacement with required-parameter enforcement.
- `PATCH /api/v1/cases/{caseId}/work-items/{projectWorkItemId}/values`
  Partial merge-aware update that respects source precedence.
- `POST /api/v1/cases/{caseId}/work-items/{projectWorkItemId}/values/confirm`
  Operator confirmation/correction workflow with audit fields.
- `GET /api/v1/cases/{caseId}/work-items/{projectWorkItemId}`
  Runtime detail returning `workItem`, current `effectiveConfiguration`, and derived `workflow` hints for operator/mobile/pricing consumers.

## Cache Strategy

- `GET /work-catalog/catalog/categories`
  Cached globally for 900 seconds under versioned `work-catalog:v2` keys.
- `GET /work-catalog/catalog/work-types`
  Cached globally for 900 seconds under versioned `work-catalog:v2` keys.
- `GET /work-catalog/catalog/work-types/{code}`
  Cached globally for 900 seconds under versioned `work-catalog:v2` keys.
- `GET /work-catalog/catalog/work-types/{code}/parameters/{parameterCode}`
  Cached globally for 900 seconds under versioned `work-catalog:v2` keys.
- `GET /work-catalog/work-types`
  Cached per tenant for 180 seconds.
- `GET /work-catalog/work-types/{code}/effective`
  Cached per tenant and work type for 180 seconds.
- `GET /cases/{caseId}/work-types/{code}/effective-configuration`
  Cached per tenant and work type for 180 seconds after an explicit project existence guard.
- `PUT /work-catalog/work-types/{code}/settings`
  Explicitly invalidates tenant-effective list, detail, and effective-configuration keys for that tenant through a shared cache helper instead of ad hoc route logic.

Hot cache layers:

- shared Redis payload cache for global catalog browse/detail reads
- shared Redis payload cache for tenant-effective catalog and workflow bootstrap reads
- request/workflow-scope in-process memoization for effective resolution, analysis profile resolution, and pricing profile resolution

Cache safety rules:

- global keys are versioned to avoid deploy-time shape mismatch
- tenant-effective keys are tenant-scoped and invalidated on settings writes
- project workflow bootstrap never serves cached data before validating project ownership
- runtime mutable work item reads stay uncached to avoid stale operator and pricing state

Runtime work item reads are intentionally uncached to avoid stale write/read races on high-churn project workflows.

## Guards

- unique constraints on global `code` and `slug`
- unique tenant override per `organization_id + work_type_id`
- unique tenant parameter override per `organization_id + work_type_parameter_id`
- unique tenant extra parameter per `organization_id + work_type_id + code`
- unique project work item sequence per `project_id + work_type_id + item_sequence`
- unique detection key per project
- centralized typed value validation in `domain.py`
- import-time parameter schema coverage guard across all six required section groups
- import-time parameter definition validation for bounds, typed defaults, and enum completeness
- DB check constraints for `work_type_parameters` default-value shape and bound ordering
- DB check constraints for `project_work_item_values` typed-value shape
- tenant pricebook lookup is verified against tenant ownership before settings are persisted
- tenant extra parameters cannot collide with global parameter codes and cannot be marked as vision-extractable
- required parameter coverage is enforced on work item creation/update
- tenant/global parameter bindings on runtime value rows are enforced via one-of DB guards
- pricing profile definitions are import-time validated for required inputs, rule targets, assumption references, and allowed source fields
- quote items store pricing profile / rule audit fields instead of opaque derived totals only
- cached project-scoped effective configuration still performs an explicit tenant/project existence guard before serving the cached payload
- cache helper records hit/miss/error metrics by namespace and operation
- service paths emit work catalog resolution latency histograms and validation failure counters for effective, analysis, and pricing resolution

## Parameter Schema Structure

Each effective work type now exposes:

- `parameters[]`
  Flat ordered list for machine consumers.
- `parameterSections[]`
  Grouped list for UI/mobile/operator rendering.

Each parameter definition includes:

- `parameterDefinitionId`
- `code`, `slug`
- `label`, `effectiveLabel`
- `description`
- `dataType`
- `unit`
- `section`, `sectionLabel`
- `required`, `enabled`
- `sortOrder`
- `minNumberValue`, `maxNumberValue`
- `visionExtractable`
- `manualOverrideAllowed`
- `default*Value`
- `enumOptions[]`

Parameter schema detail additionally exposes:

- analysis extraction/output/validation bindings for the parameter
- pricing required-input / base-rule / adjustment bindings for the parameter
- explicit `supportsVisionPopulation` and `supportsPricingInput` flags for downstream orchestration

Required section groups:

- `dimensions`
- `materials`
- `condition_or_damage`
- `access_and_complexity`
- `quantity_scope`
- `optional_notes`

## Example Work Types

- `roof-repair`
  Repair area, roof pitch, covering type, damage type, severity band, access method, repair zones, notes.
- `chimney-renovation`
  Renovation area, stack height, chimney material, masonry damage type, severity, roof access, repair zones, notes.
- `tile-installation`
  Tile area, tile size, tile system type, substrate condition, interior access, room count, notes.
- `window-installation`
  Window count, opening width/height, frame material, opening condition, access method, existing-unit removal flag, notes.
- `electrical-installation`
  Scope description, route length, electrical system type, site condition, service access, circuit count, notes.
- `foundation-work`
  Concrete volume, foundation depth, foundation system type, ground condition, site access method, pour zones, notes.
- `cleaning-after-construction`
  Cleaning area, ceiling height, surface type, contamination level, access method, waste bag count, notes.
- `emergency-repair`
  Incident count, response time, affected system, incident type, severity, access method, temporary stabilization flag, notes.

## Runtime Validation And Storage

- Tenant-effective schema is resolved from the global catalog plus sparse tenant overrides.
- Tenant defaults are materialized into runtime value rows with normalized `source_type = default`, so defaults influence execution instead of staying as UI-only hints.
- Each submitted `parameterCode` must exist, be enabled, and satisfy the effective `required` set.
- Typed coercion validates scalar shape, enum membership, numeric bounds, `visionExtractable`, and `manualOverrideAllowed`.
- Runtime values are stored in `project_work_item_values` with a one-of definition binding to either `work_type_parameter_id` or `tenant_work_type_extra_parameter_id`, plus immutable snapshot fields for code/name/data type/unit.

## Why This Is A Core Subsystem

This subsystem gives NOVU Builder one durable place where work semantics live. Routes, UI, pricing, and vision integrations resolve through the same definitions instead of carrying their own `if/elif` work-type logic. That keeps the platform evolvable: adding a new work type means inserting catalog data and optionally extending orchestrators, not refactoring application-wide branching.
