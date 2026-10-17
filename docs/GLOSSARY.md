# Glossary

Canonical NOVU Builder terminology. Use these terms **exactly**; do not introduce synonyms. When code and
prose disagree, this glossary defines the intended meaning.

| Term | Meaning |
|---|---|
| **Case** | Customer project container — the unit of work; has a status state machine (draft → intake → analyzing → proposal_ready → quote_ready → sent → archived). |
| **Analysis** | AI-generated measurements from photos, **before** pricing. |
| **Measurement** | An AI estimation (quantity / area / condition) awaiting validation. Never a price. |
| **Offer** | A server-side, priced commercial proposal derived from validated measurements. |
| **Proposal** | A validated, priced offer prepared to send to the client. |
| **Pricing Engine** | The **single source of pricing truth** (catalog formula engine). Only it produces money values ([ADR-0001](ARCHITECTURE_DECISION_RECORDS/ADR-0001-ai-pricing.md)). |
| **Analysis Profile** | Configuration controlling how analysis behaves for a work type. |
| **Pricing Profile** | Configuration controlling how pricing is computed for a work type. |
| **Work Type** | A classified kind of work in the catalog (leaf or composite). |
| **Work Catalog** | The global, tenant-overridable catalog of work types and their parameters. |
| **Worker** | A background processing service. Runs in isolated lanes (analysis / heavy / offer). |
| **Job** | A long-running asynchronous task processed by a worker, with lease + idempotency. |
| **Outbox** | Table of domain events written in the same transaction as the state change ([ADR-0005](ARCHITECTURE_DECISION_RECORDS/ADR-0005-event-driven-processing.md)). |
| **Tenant / Organization** | An isolated customer account; all data is scoped to it and never crosses tenant boundaries. |
| **`pricing_status`** | Offer field; `"pending"` until the Pricing Engine has computed prices. |
