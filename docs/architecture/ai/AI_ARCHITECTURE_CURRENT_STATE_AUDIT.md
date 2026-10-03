# NOVU AI Architecture — Current State Audit

**Milestone:** M1 Architecture Contracts  
**Audited baseline:** `master` at `5c1847ea265a0af970f0839ef1e8c12ff464598b`  
**Audit mode:** read-only inspection of runtime code; documentation changes only on `docs/ai-architecture-m1`.  
**Release boundary:** v0.8.6 has not yet passed staging acceptance.

## 1. Executive Summary

The current backend already contains several strong building blocks for the future NOVU AI System, but they are split across two partially independent AI paths:

1. the vision/analysis path under `app.ai` and `AnalysisService`;
2. the offer-processing path under `app.offer_processing`, which already has a stronger provider abstraction, immutable-ish per-call `AgentRun` records, AI budget accounting and transactional outbox/SSE infrastructure.

The correct direction is **consolidation through contracts**, not creating a third AI stack.

The current system is not yet the Foundation target. Missing pieces include a generic Agent/Capability/Workflow Registry, generic evidence/uncertainty model, deterministic AI Policy Engine, generic Model Router, Tool/Human Gateways, unified semantic AI Event Ledger, verifier/auditor roles, Objectives & Constraints, Optimizer, formal Decision records, Champion/Challenger and benchmark/learning governance.

No runtime change is recommended before v0.8.6 staging/release.

---

## 2. EXISTS AND REUSABLE

### 2.1 Provider abstraction and fail-closed provider capability checks

**Files**
- `python-backend/app/ai/analysis_service.py`
  - `PROVIDERS`
  - `get_analysis_provider()`
  - `run_project_analysis()`
- `python-backend/app/core/analysis_provider_capabilities.py`
  - `AnalysisProviderCapability`
  - `validate_selected_analysis_provider()`
- `python-backend/app/offer_processing/provider.py`
  - `ProviderRequest`
  - `ProviderResponse`
  - `ProviderAdapter`

**Assessment**

There is already a meaningful separation between provider selection and business services. The offer-processing `ProviderAdapter` contract is especially reusable because it records model/provider identity, token usage, build and cost, while the vision path has explicit provider capability metadata and blocks unimplemented OpenAI fail-closed.

This is a strong seed for the future Model Router, but it should be generalized around capability/quality/risk rather than provider keys.

### 2.2 Staged AI pipeline abstraction

**File**
- `python-backend/app/ai/pipeline.py`
  - `StagedVisionPipeline`
  - `LegacyProviderAdapter`
  - `PipelineOrchestrator`

**Assessment**

The detect → extract → catalog-map split already moves toward small responsibility stages and explicit contracts. The legacy adapter provides migration safety. This is reusable design experience for future workflows, though it remains vision-specific and provider-oriented rather than a generic Workflow Registry.

### 2.3 Structured analysis persistence, retry and failure history

**Files**
- `python-backend/app/models/domain.py`
  - `AnalysisJob`
  - `AnalysisResult`
- `python-backend/app/services/analysis_service.py`
- `python-backend/app/repositories/analysis_repository.py`
- `python-backend/app/worker/queue.py`

**Existing useful concepts**

- job status state machine;
- attempt/retry counts;
- worker/lease ownership;
- input payload + offloaded input storage key;
- output summary;
- error message + traceback;
- model name/version on analysis result;
- durable Redis queue, lease/ack, retry and DLQ;
- deterministic classification of retryable/non-retryable failures.

These are valuable seeds for agent-run lifecycle, operational intelligence and immutable attempt history.

### 2.4 `AgentRun` is a strong seed for a generic AI run record

**File**
- `python-backend/app/models/offer_processing.py`
  - `AgentRun`

The model already records:

- frozen/anonymized input snapshot reference/hash;
- version context;
- provider;
- model and model build;
- prompt/completion token counts;
- estimated cost;
- raw and parsed output;
- validation errors;
- error details;
- start/completion timestamps;
- status/outcome.

This is conceptually close to the Foundation's run record and should be studied as a migration/reuse candidate instead of inventing an unrelated run representation.

### 2.5 AI cost governance exists

**Files**
- `python-backend/app/models/offer_processing.py`
  - `OrganizationAiBudget`
  - `AiBudgetReservation`
- `python-backend/app/offer_processing/budget.py`
  - `BudgetService`

There is atomic reservation, actual-cost accounting, crash recovery for stale reservations and tenant-level limits. This can later feed model routing and AI cost telemetry.

Foundation rule still applies: cost must not override minimum quality/risk thresholds for critical tasks.

### 2.6 Transactional outbox and SSE infrastructure

**Files**
- `python-backend/app/models/offer_processing.py`
  - `OutboxEvent`
- `python-backend/app/offer_processing/outbox.py`
  - `build_outbox_event()`
  - `OutboxPublisher`
- `python-backend/app/core/metrics.py`

Current outbox provides transactionally coupled events, monotonic sequence, at-least-once publication and SSE replay/observability. This is a strong transport foundation.

Important distinction: the future **semantic AI Event Ledger** is not identical to the current transport outbox. Outbox delivery flags are mutable transport state; AI decision history requires richer immutable lineage semantics.

### 2.7 Existing immutable/append-style audit concepts

**File**
- `python-backend/app/models/domain.py`
  - `AuditLog`
  - `ProjectStatusHistory`

Both represent useful audit patterns. `ProjectStatusHistory` explicitly documents never-update/delete transition history.

### 2.8 Work catalog / analysis profile contracts

**Files**
- `python-backend/app/services/analysis_profile_service.py`
- `python-backend/app/repositories/work_catalog_repository.py`
- `python-backend/app/models/work_catalog.py`

Current catalog/profile structures include extraction rules, validation rules, confidence thresholds and output mappings. These provide valuable deterministic/domain configuration that future agents and Policy Engine can consume rather than embedding rules solely in prompts.

### 2.9 Storage abstraction

**File**
- `python-backend/app/storage/backend.py`

Local vs S3 storage is already selected behind a backend dispatcher. This is a good precedent for Tool Gateway adapters and future evidence/object references.

### 2.10 Operational observability foundation

**Files**
- `python-backend/app/core/metrics.py`
- `python-backend/app/api/routes/system.py`
- `python-backend/app/worker/heartbeat.py`
- `python-backend/app/main.py`

Existing signals include HTTP metrics, DB/storage/Redis readiness, worker heartbeat, queue length, retry/DLQ state, job duration/failure, backpressure, audit-write failures, catalog validation metrics and outbox/SSE metrics.

The backend also has fail-fast startup schema/storage/Redis checks. These signals are useful raw inputs for future Operational Intelligence.

### 2.11 Human/manual override seeds

**File**
- `python-backend/app/models/domain.py`

Examples:
- `AnalysisResult.manual_area_sqm`
- `AnalysisResult.final_area_source`
- `QuoteItem.is_manual_override`

These show existing product semantics for human override, but they are not yet a general Human Gateway with lineage.

---

## 3. EXISTS BUT NEEDS ADAPTATION

### 3.1 Two AI abstractions must converge conceptually

The vision stack (`app.ai`) and offer-processing stack (`app.offer_processing`) solve overlapping provider/runtime concerns differently.

**Risk:** implementing the Foundation directly beside them could create a third stack.

**Adaptation direction:** M2 should define compatibility/adapters around the strongest existing contracts, then migrate incrementally. Do not rewrite both systems at once.

### 3.2 Provider registry is hard-coded

`app.ai.analysis_service.PROVIDERS` is a Python dictionary keyed by provider name. Provider capability configuration in `analysis_provider_capabilities.py` is also static.

This is acceptable today, but the Foundation requires Agent/Capability/Model routing based on declared capabilities, quality, risk and approval state.

### 3.3 Current pipeline is specialized and returns legacy shape

`PipelineOrchestrator` is vision-specific and ends by converting back to a legacy result contract. It proves staged orchestration is feasible but is not a generic Workflow Registry.

### 3.4 Claude vision prompt is embedded in code

**File**
- `python-backend/app/ai/providers/claude_vision_provider.py`
  - `_SYSTEM_PROMPT`
  - `ClaudeVisionProvider.analyze_project()`

The provider records a hard-coded `modelVersion = "1.0"`, while prompt content is not represented by a first-class prompt version in the returned result. Future Foundation lineage requires explicit prompt/version identity.

### 3.5 Evidence and confidence are partial

Vision analysis carries `area_confidence`, catalog extraction can carry per-attribute confidence, and validation warnings exist. However, there is no universal distinction among FACT / INFERENCE / ASSUMPTION / DECISION, no unified provenance object, no alternative-hypothesis representation and no generic critical-unknown contract.

### 3.6 Outbox must remain transport, not become the whole Event Ledger

Current `OutboxEvent` lacks generic workflow/run/correlation/causation/source/target/model/prompt/security/redaction semantics required by the Foundation.

Do not overload the existing table during v0.8.6. Future design should decide whether semantic events are persisted separately and projected to outbox for transport, or whether a compatible append-only event model can feed the outbox.

### 3.7 Audit logs are useful but not full AI lineage

`AuditLog` is actor/resource oriented, not a complete agent/workflow evidence graph. It should remain security/business audit infrastructure; the AI event contract should not be reduced to this schema.

### 3.8 Direct DB/session access is widespread

Examples inspected:
- `app.services.analysis_service` directly uses `AsyncSessionFactory` and `WorkerAsyncSessionFactory`.
- `app.api.routes.system` directly uses `AsyncSessionFactory`.
- repositories/services receive SQLAlchemy sessions directly.

This is not a defect for the current app, but future agents must not inherit arbitrary DB access. Tool Gateway should expose scoped capabilities rather than handing agents DB sessions.

### 3.9 Cost accounting is offer-specific

`AgentRun`/budgeting is tied to `OfferJob`/organization. A future generic AI run system needs cost/usage across all agent roles and domains without losing the proven reservation/accounting logic.

---

## 4. MISSING

The following Foundation concepts are not currently present as generic architecture:

- Agent Registry;
- Capability Registry;
- Workflow Registry;
- generic Agent Contract enforcement;
- semantic AI Event Ledger with full lineage;
- generic evidence/provenance model;
- universal uncertainty model;
- explicit verifier role contracts;
- auditor/meta-auditor contracts;
- Objectives & Constraints stage;
- Optimizer;
- generic Decision / Policy record;
- deterministic AI Policy Engine;
- generic Model Router based on benchmarks/risk/capability;
- Tool Gateway for agent permissions;
- Human Gateway with formal states and lineage;
- per-capability Champion/Challenger lifecycle;
- benchmark/evaluation framework;
- golden dataset governance;
- shadow evaluation framework;
- self-hosted model lifecycle;
- Operational Intelligence RCA/remediation/recovery chain;
- approved/versioned recovery runbook gateway;
- prompt registry/version governance shared across AI paths.

---

## 5. CONFLICTS WITH FOUNDATION

### 5.1 Claude prompt asks the model to produce prices

`python-backend/app/ai/providers/claude_vision_provider.py` instructs the model to return material unit/total prices.

In contrast, `python-backend/app/offer_processing/provider.py` explicitly states the safer architecture: AI returns measurements and **does not produce prices**; deterministic tenant pricing remains the source of pricing truth.

The latter aligns better with the Foundation separation-of-responsibility principle. This inconsistency is a significant future consolidation finding, but it must **not** be changed before v0.8.6 staging/release.

### 5.2 Provider/model identity is sometimes implementation detail instead of policy result

The vision path chooses a provider key directly. Future critical tasks require capability/risk/quality-based routing and approved Champion state.

### 5.3 Confidence may be treated as a scalar without structured uncertainty

Foundation explicitly requires missing information, alternatives and critical unknowns in addition to confidence.

### 5.4 Current staged path mixes domain stages with provider protocol

`StagedVisionPipeline` asks one provider object to implement detect/extract/map-to-catalog. Foundation expects independently replaceable specialist capabilities and verifiers. This is a migration concern, not a reason to discard the current abstraction.

---

## 6. TECHNICAL DEBT / RISKS

1. **Third-stack risk** — adding a new kernel without adapters would leave vision, offer and kernel provider/orchestration stacks side by side.
2. **Lineage fragmentation** — AnalysisJob/AnalysisResult, AgentRun, AuditLog, ProjectStatusHistory and OutboxEvent each preserve different parts of history.
3. **Prompt/version traceability** — not uniform across AI paths.
4. **AI-produced pricing in legacy vision** — violates the desired deterministic pricing separation.
5. **No generic permission boundary for future agents** — direct service/repository patterns are safe for trusted application code but not suitable as agent tools.
6. **No benchmark gate** — current provider/model selection is not tied to NOVU task benchmarks.
7. **No formal uncertainty calibration** — false confidence cannot yet be measured as a first-class cross-agent metric.
8. **Operational automation risk** — current retries/reapers are deterministic and good; future AI recovery must not bypass that safety with arbitrary generated commands.
9. **Schema coupling** — current run/event models are tied to specific domain jobs. Reuse should preserve data/history while introducing generic contracts carefully.
10. **Release timing** — structural changes now could invalidate the v0.8.6 staging candidate.

---

## 7. DO NOT TOUCH BEFORE v0.8.6 RELEASE

Until staging acceptance is complete, do not change:

- `app.ai` provider selection or pipeline behavior;
- `app.offer_processing` provider/runtime behavior;
- AnalysisJob/AnalysisResult/AgentRun schemas;
- OutboxEvent schema or SSE transport;
- AuditLog/ProjectStatusHistory;
- Redis queue/lease/retry/DLQ behavior;
- worker orchestration/heartbeats;
- work catalog/profile resolution;
- pricing/catalog behavior;
- storage backend behavior;
- FastAPI routes/auth/permissions;
- DB session routing;
- Alembic schema;
- deployment/Compose/CI release gates;
- production dependencies/environment variables.

If staging exposes a blocker, fix it in a separate release-blocker PR and repeat the relevant acceptance checks.

---

## 8. RECOMMENDED POST-v0.8.6 IMPLEMENTATION ORDER

### M1 — Architecture Contracts
**Status:** this documentation milestone.

### M2 — Kernel skeleton + compatibility adapters
Implement only the smallest kernel contracts:
- typed Agent/Capability/Workflow manifests;
- registries;
- orchestrator interface;
- adapters around existing vision/offer paths;
- no wholesale migration.

**Reason:** prevent a third AI stack.

### M3 — Semantic Event Ledger + correlation + observability bridge
Define append-only AI semantic events and projections to existing outbox/telemetry. Preserve existing SSE/outbox transport.

### M4 — Measurement reference pipeline
Use a narrow domain chain:
Measurement → Verifier → Auditor → Objectives/Constraints → Optimizer → Decision.

Reuse existing analysis/catalog contracts where possible.

### M5 — Operational Intelligence reference pipeline
Start read-only:
Log normalization → classification → correlation → RCA → RCA verifier → remediation recommendation → operational audit.

No autonomous production recovery yet.

### M6 — Benchmark & Evaluation Framework
Create task-specific datasets/metrics before introducing self-hosted models or Champion/Challenger promotion.

### M7 — First domain package
Prefer a domain with strong real-world labeled cases and clear deterministic checks (Facade is a likely candidate, but data quality should decide).

### M8 — Second domain package
Use a structurally different domain (e.g. Waterproofing) to prove extensibility.

### M9 — Model Router + Champion/Challenger
Only after benchmark evidence exists.

### M10 — Learning Dataset Pipeline
Govern verified human corrections, final outcomes and dataset eligibility.

### M11 — Self-hosted model experiments
Run as Challenger/shadow. Do not make ownership a quality signal.

### M12 — NOVU model Challenger
Promotion only if measured quality/risk requirements are met.

---

## 9. First implementation recommendation after v0.8.6

Do **not** start by creating many agents.

Start by building a minimal registry/orchestrator compatibility layer that can describe and invoke two existing behaviors as capabilities without changing their semantics:

1. one existing vision/measurement path;
2. one read-only operational/log-analysis prototype.

If both fit the same contracts without domain-specific kernel branches, the M1 abstractions are validated.

---

## 10. M1 confirmation

This milestone is documentation-only.

- Runtime: unchanged.
- DB schema: unchanged.
- Alembic migrations: unchanged.
- Production behavior: unchanged.
- Production dependencies: unchanged.
- Deployment/CI: unchanged.
