# AI Evidence Model

## Purpose

NOVU must distinguish what is observed from what is inferred, assumed or decided.

## Assertion classes

- **FACT** — directly supported by authoritative or raw evidence.
- **INFERENCE** — reasoned conclusion derived from evidence.
- **ASSUMPTION** — explicit temporary premise used because information is missing.
- **DECISION** — selected action/option after verification, objectives, optimization and policy.

An assertion cannot silently change class.

## Evidence source types

- PHOTO
- DOCUMENT
- MEASUREMENT
- CATALOG
- DATABASE
- CALCULATION
- HUMAN_INPUT
- MODEL_INFERENCE
- SYSTEM_LOG
- METRIC
- TRACE
- EXTERNAL_API
- TOOL_OUTPUT

## Evidence reference

```yaml
evidence_id: string
source_type: enum
source_reference: immutable-or-versioned-ref
captured_at: timestamp|null
producer: actor-ref
content_hash: string|null
security_classification: string
redaction_status: string
strength: direct|strong|moderate|weak
```

## Uncertainty

Confidence is not sufficient. Important results should preserve:

```yaml
uncertainty:
  confidence: 0..1|null
  type:
    - missing_information
    - visual_ambiguity
    - measurement_error
    - model_disagreement
    - conflicting_evidence
    - extrapolation
    - external_dependency
    - unknown
  measurement_tolerance: string|null
  missing_information: []
  alternative_hypotheses: []
  critical_unknowns: []
```

## Conflict representation

Conflicts are explicit records between assertions/evidence and include the conflicting references, conflict type, severity, resolver requirement and resolution event.

## Rules

- Missing evidence cannot be replaced by confidence.
- A model-generated statement is not a FACT merely because confidence is high.
- Measurement tolerance must be kept in the same lineage as the quantity.
- Human correction preserves the original result and creates a new authoritative event.
- Final results should expose critical unknowns when they materially affect the decision.
