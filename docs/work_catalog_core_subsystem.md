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
  Global pricing strategy profile. This is intentionally separate from existing tenant `PricingProfile` pricebooks.

### Tenant Effective Layer

- `TenantWorkTypeSetting`
  Per-tenant override record without duplicating global rows. Stores enablement, display override, resolved profile overrides, and tenant pricebook linkage.
- `TenantWorkTypeParameterOverride`
  Sparse per-tenant delta for parameter behavior. Supports required/optional/hidden transitions, display-name override, ordering override, and typed default override without cloning the global parameter schema.

### Runtime Project Layer

- `ProjectWorkItem`
  Runtime project entity created from effective work type resolution. Stores immutable snapshot fields needed for audit and long-term correctness.
- `ProjectWorkItemValue`
  Typed value rows bound to `WorkTypeParameter`, with resolved parameter metadata snapshot.

### Vision Layer

- `VisionDetection`
  Detection/event log linked to project, work type, optional work item, optional analysis job, and optional photo reference.

## Boundaries

### Global

- owns catalog codes, slugs, parameters, options, and default analysis/pricing profiles
- does not store tenant-specific copies
- changes are versioned via `catalog_version` / `profile_version`

### Tenant

- stores only deltas from global definitions
- links a tenant to an existing global work type
- may override enablement, display name, analysis profile, catalog pricing profile, and tenant pricebook
- avoids per-tenant catalog duplication

### Runtime

- stores resolved snapshot fields on `ProjectWorkItem` and `ProjectWorkItemValue`
- remains historically correct even when the global catalog evolves later
- supports multiple items of the same work type per project via `item_sequence`

### Vision

- keeps raw detection facts separate from catalog and runtime projections
- allows future re-linking, rejection, or replay without mutating catalog definitions

## Scaling Design

- machine-readable `code` / `slug` values are globally unique and index-backed
- tenant overrides are sparse and delta-based, so 100k tenants do not require catalog row duplication
- runtime rows denormalize `organization_id`, resolved codes, and version fields for hot tenant/project lookups
- project work items use compound indexes for `organization_id + project_id + status`
- vision detections use compound indexes for `organization_id + project_id + status`
- effective catalog reads are cacheable because the source of truth is stable and invalidation is explicit on tenant override writes

## Cache Strategy

- `GET /work-catalog/work-types`
  Cached per tenant for 60 seconds.
- `GET /work-catalog/work-types/{code}/effective`
  Cached per tenant and work type for 60 seconds.
- `PUT /work-catalog/work-types/{code}/settings`
  Explicitly invalidates both list and item keys for that tenant.

Runtime work item reads are intentionally uncached to avoid stale write/read races on high-churn project workflows.

## Guards

- unique constraints on global `code` and `slug`
- unique tenant override per `organization_id + work_type_id`
- unique tenant parameter override per `organization_id + work_type_parameter_id`
- unique project work item sequence per `project_id + work_type_id + item_sequence`
- unique detection key per project
- centralized typed value validation in `domain.py`
- import-time parameter schema coverage guard across all six required section groups
- import-time parameter definition validation for bounds, typed defaults, and enum completeness
- DB check constraints for `work_type_parameters` default-value shape and bound ordering
- DB check constraints for `project_work_item_values` typed-value shape
- tenant pricebook lookup is verified against tenant ownership before settings are persisted
- required parameter coverage is enforced on work item creation/update

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
- Each submitted `parameterCode` must exist, be enabled, and satisfy the effective `required` set.
- Typed coercion validates scalar shape, enum membership, numeric bounds, `visionExtractable`, and `manualOverrideAllowed`.
- Runtime values are stored in `project_work_item_values` with a foreign key to `work_type_parameter_id` plus immutable snapshot fields for code/name/data type/unit.

## Why This Is A Core Subsystem

This subsystem gives NOVU Builder one durable place where work semantics live. Routes, UI, pricing, and vision integrations resolve through the same definitions instead of carrying their own `if/elif` work-type logic. That keeps the platform evolvable: adding a new work type means inserting catalog data and optionally extending orchestrators, not refactoring application-wide branching.
