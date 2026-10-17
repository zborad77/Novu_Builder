# Tenant Override Subsystem

## Purpose

Tenant overrides in NOVU Builder are modeled as sparse deltas over the global work catalog.
The subsystem lets each tenant:

- enable or disable work types,
- select a tenant-specific analysis profile override,
- select a tenant-specific catalog pricing profile override,
- apply tenant defaults to global parameters,
- add controlled tenant extra parameters without cloning global catalog rows.

## Data Model

- `TenantWorkTypeSetting`
  Central per-tenant override root keyed by `organization_id + work_type_id`.
- `TenantWorkTypeParameterOverride`
  Sparse override for global parameters only.
- `TenantWorkTypeExtraParameter`
  Controlled tenant extension definition layered over the global work type.
- `TenantWorkTypeExtraParameterOption`
  Allowed enum values for tenant extra option parameters.

Tenant extra parameters are intentionally constrained:

- codes and slugs must start with `tenant.`,
- they cannot overwrite global parameter codes,
- they cannot be `visionExtractable` until tenant-specific analysis mappings are versioned,
- they are stored only for tenants that actually use them.

## Effective Resolution Flow

`TenantWorkTypeResolutionService` composes:

1. global `WorkType`,
2. sparse `TenantWorkTypeSetting`,
3. sparse `TenantWorkTypeParameterOverride`,
4. sparse `TenantWorkTypeExtraParameter`,
5. effective analysis profile,
6. effective catalog pricing profile.

The result is a single resolved configuration object used by:

- effective catalog reads,
- runtime work item validation,
- analysis profile resolution,
- pricing profile resolution.

## Runtime Value Storage

`ProjectWorkItemValue` now supports a strict one-of binding:

- `work_type_parameter_id` for global parameters,
- `tenant_work_type_extra_parameter_id` for tenant extra parameters.

`resolved_parameter_scope` stores whether the row came from the global schema or the tenant extension layer.
Defaults are materialized as runtime rows with normalized `source_type = default`, so tenant defaults affect execution, not just UI hints.

## Scaling Characteristics

- No tenant copies of `work_types`, `work_type_parameters`, analysis profiles, or pricing profiles.
- Tenant overrides are sparse and indexed by `organization_id + work_type_id`.
- Tenant extra parameters exist only where needed.
- Effective reads remain predictable because global catalog rows stay canonical and tenant lookups are scoped and indexed.

## Guards

- unique tenant setting per work type and tenant,
- unique tenant extra parameter code per tenant/work type,
- unique tenant extra parameter option code per tenant parameter,
- runtime one-of parameter binding guard for global vs tenant extra definitions,
- central validation for tenant extra parameter schema,
- collision guard against reusing a global parameter code in tenant extras.
