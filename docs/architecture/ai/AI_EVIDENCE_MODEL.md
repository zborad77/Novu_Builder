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
evidence_version: exact-version
schema_version: semver
source_type: enum
source_reference: immutable-or-versioned-ref
captured_at: timestamp|null
producer: actor-ref
content_hash: string|null
security_classification: string
redaction_status: string
strength: direct|strong|moderate|weak
scope: ScopeRef
event_time: timestamp|null
recorded_at: timestamp
valid_from: timestamp|null
valid_until_or_freshness_rule: policy-ref|null
source_trust_ref: versioned-trust-assessment
completeness_ref: requirements-and-coverage-ref
retention_policy_ref: exact-version-ref
data_use_constraints_ref: immutable-ref
```

## Assertion and transformation graph

```yaml
assertion_id: string
assertion_version: exact-version
schema_version: semver
scope: ScopeRef
class: FACT|INFERENCE|ASSUMPTION|DECISION
statement_value_ref: immutable-ref
evidence_links: []                    # evidence exact revision, supports/contradicts/qualifies
derived_from: []                      # multiple exact assertion/evidence input refs
transformation_ref: immutable-ref|null
uncertainty_ref: immutable-ref
captured_or_event_time: timestamp|null
valid_from: timestamp|null
valid_until_or_freshness_rule: policy-ref|null
source_trust_ref: versioned-trust-assessment
completeness_ref: requirements-and-coverage-ref
missing_required_evidence: []
candidate_refs: []                    # exact revisions
decision_refs: []                     # exact revisions
supersedes_refs: []
conflict_refs: []
creation_event_ref: semantic-event-ref
```

A transformation records ID/version, type (observation, calculation, inference, aggregation, human correction or another declared operation), exact input/output refs, producer/run/attempt/call IDs, execution binding set, event time and reason. Record the applicable model artifact/assurance identity, prompt, provider/adapter, tool contract and deterministic evaluator versions; non-applicable identities are explicitly absent. A derived value cannot have a provenance-free transformation.

Evidence-to-assertion links distinguish support, contradiction and qualification. Multi-input transformations preserve all material inputs and parameter/context refs. Raw evidence remains distinct from interpretation. A raw source or trusted human role does not by itself establish truth: FACT requires the declared evidence/support criteria; a changed class requires a new explicitly justified assertion version.

Freshness rules distinguish capture/event time from recording/processing time and declare the relevant validity interval or evaluation rule. Candidate/decision finalization evaluates freshness, trust, completeness and required evidence against its bound context, not only against high confidence. Stale or missing required evidence causes the Workflow Contract's wait/block/insufficient-evidence handling. No universal domain freshness duration is assigned in M1.

Supersession creates a new version and records why/when the predecessor ceased to be applicable; it never mutates old claims or silently migrates old decisions. Human corrections follow Human Gateway authority/fencing while retaining the corrected assertion and its provenance.

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

Conflict records bind the exact conflicting revisions, affected candidate/context/decision refs, unresolved/resolved state, authorized resolver and resolution rationale. Resolution references supporting evidence and any superseding assertion; dismissing an alternative is itself traceable. An unresolved critical conflict prevents finalization unless the bound Policy explicitly permits a recorded, lawful exception.

Required evidence declarations identify requirement/version, expected source/coverage, freshness/trust criteria and the supplying or missing refs. Decision records reference those evaluations so NOVU can answer what was absent as well as what supported the selected conclusion.

## Privacy, retention and untrusted evidence

Tenant/platform scope applies to evidence, assertion, transformation and all joined objects. Data classification drives hard recipient/egress/locality/retention/data-use restrictions, including external tool exposure. Redaction creates a separately identified derivative with recorded transformation; it does not replace the original or erase its governed retention obligations.

Use immutable/versioned object references and integrity metadata, not large raw payload copies in the semantic Ledger. Scope checks apply to retrieval and replay. Presigned URLs are temporary access credentials bound to object/version, purpose/recipient and expiry; they are not evidence identity and must not be exposed in broadly accessible logs/events. Raw provider/tool output has an explicit retention/access policy independent of curated assertions.

Evidence contents, documents, photos, logs and retrieved/provider/tool output are untrusted **data**, never authority to change instructions, policy, tools, tenant, budget or approval gates. Trusted prompts/context boundaries, structured validation and Gateway authorization remain outside that data. Prompt-injection attempts and blocked exposures create scoped security observations without copying secrets into the ledger.

Training/benchmark/RAG eligibility requires recorded legal basis/consent where applicable, permitted provider/data use, tenant scope, retention, redaction, quality verification and dataset governance approval. Human correction or production outcome alone never grants eligibility. Govern erasure/access revocation through new attributed retention events as defined by the Event Contract; immutability is not indefinite PII retention.

## Rules

- Missing evidence cannot be replaced by confidence.
- A model-generated statement is not a FACT merely because confidence is high.
- Measurement tolerance must be kept in the same lineage as the quantity.
- Human correction preserves the original result and creates a new authoritative event.
- Final results should expose critical unknowns when they materially affect the decision.
