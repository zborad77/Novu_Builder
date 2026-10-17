# Analysis Profile Subsystem

## Purpose

The analysis profile subsystem turns catalog-driven vision behavior into a first-class core module.
Each analyzable work type resolves to an explicit versioned analysis contract instead of ad hoc prompt text or service-level branching.

## Model

`catalog_analysis_profiles`
- Stable machine-readable `code`
- Integer `profile_version`
- Lifecycle `status`
- `scope_code`, `scope_label`, `scope_description`
- `provider_family`, `task_type`, output contract version
- Fallback behavior with explicit mode and instructions

Child entities:
- `catalog_analysis_profile_target_objects`
- `catalog_analysis_profile_ignored_objects`
- `catalog_analysis_profile_extraction_rules`
- `catalog_analysis_profile_validation_rules`
- `catalog_analysis_profile_confidence_thresholds`
- `catalog_analysis_profile_output_mappings`

This keeps analysis configuration explicit, queryable, auditable, and extendable without moving logic into prompt blobs.

## Effective Resolution Flow

1. Resolve global work type by stable `workTypeCode`.
2. Resolve tenant setting override when present.
3. Pick the effective analysis profile.
4. Enforce active profile status and work-type/profile consistency guard.
5. Build provider-facing analysis config from the resolved profile snapshot.
6. Persist the chosen `analysis_profile_id`, `analysis_profile_code`, `analysis_profile_version`, and `work_type_code` into the analysis job.
7. Re-load the same snapshot during execution so queued jobs cannot drift to newer tenant settings.
8. Validate provider output against extraction rules, confidence thresholds, and validation guards before persisting runtime output.

## Runtime Mapping

Output mappings translate provider attributes into:
- `analysis_results` summary fields
- `project_work_item` measured quantity hints
- `project_work_item_value` parameter payload hints

The current implementation persists the resolved analysis summary and validated catalog attribute payload, while exposing runtime mapping artifacts for downstream work-item materialization.

## Scaling Notes

- Profiles are stored once globally, not copied per tenant.
- Tenant-specific behavior stays in sparse override rows.
- Hot reads can be cached on the effective work type path.
- Child tables are indexed by `analysis_profile_id` and sort order for predictable read amplification.
- Jobs and results carry resolved snapshot fields so analytics and audits do not need historical catalog reconstruction.
