# Pricing Profile Subsystem

## Purpose

`CatalogPricingProfile` is the pricing source-of-truth companion to `WorkType` and `AnalysisProfile`.
It keeps pricing logic out of routes, UI adapters, and ad hoc quote services by expressing pricing as explicit catalog data:

- required runtime inputs,
- base pricing rules,
- surcharge / adjustment rules,
- labor assumptions,
- material assumptions,
- minimum job charge,
- versioned active profile resolution.

## Model

The subsystem is centered on `catalog_pricing_profiles` and five child tables:

- `catalog_pricing_profile_required_inputs`
- `catalog_pricing_profile_base_rules`
- `catalog_pricing_profile_adjustment_rules`
- `catalog_pricing_profile_labor_assumptions`
- `catalog_pricing_profile_material_assumptions`

Each profile carries:

- `code`
- `profile_version`
- `status`
- `pricing_basis`
- `currency`
- `pricing_strategy`
- `labor_rate_source`
- `material_pricing_source`
- `min_job_price`
- `metadata_json`

## Resolution Flow

1. Resolve `WorkType` from the global catalog.
2. Apply sparse `TenantWorkTypeSetting` override if present.
3. Resolve the effective active `CatalogPricingProfile`.
4. Resolve the tenant `PricingProfile` override or fall back to the tenant default pricebook.
5. For runtime pricing, prefer the `ProjectWorkItem` snapshot (`catalog_pricing_profile_id`, `tenant_pricing_profile_id`, resolved code/version fields) so later catalog changes do not rewrite historical pricing decisions.

## Execution Flow

`PricingProfileService` executes pricing in four steps:

1. Validate declared required inputs against runtime `ProjectWorkItemValue` rows and snapshot fields.
2. Evaluate base rules into explainable labor / material / other line items.
3. Apply conditional adjustment rules without work-type branching.
4. Enforce `min_job_price` via an explicit minimum-charge adjustment line.

The output contains:

- resolved catalog pricing profile code/version,
- input snapshot used for the calculation,
- explainable line items with pricing rule codes,
- labor / material / other subtotals,
- minimum-charge adjustment,
- total before margin and VAT.

## Quote Variant Integration

`QuoteVariantService` now prefers runtime `ProjectWorkItem` pricing whenever project work items exist.
Each `QuoteItem` stores:

- `project_work_item_id`
- `work_type_code`
- `catalog_pricing_profile_id`
- `resolved_catalog_pricing_profile_code`
- `resolved_catalog_pricing_profile_version`
- `catalog_pricing_rule_code`

This makes quote output auditable at the exact rule level.

## Scaling Notes

- Global pricing profiles are shared across tenants; tenant customization remains sparse.
- Rule tables are indexed by `catalog_pricing_profile_id + sort_order`.
- Runtime work items snapshot pricing profile identity, avoiding historical replay joins.
- Project quote generation reads already-resolved work item snapshots instead of re-deriving pricing semantics from free text.

## Current Basis Examples

- `roof-repair`: `area`
- `chimney-new-build`: `count`
- `gutter-installation`: `length`
- `foundation-work`: `volume`
- `electrical-installation`: `scope`
- `roof-inspection`: `inspection`
- `maintenance`: `service`
- `emergency-repair`: `incident`
