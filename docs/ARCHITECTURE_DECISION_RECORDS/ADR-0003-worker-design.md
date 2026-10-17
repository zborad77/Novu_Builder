# ADR-0003 — Worker design: isolated lanes, fencing, idempotency

**Status:** Accepted

## Context
Background processing spans fast AI analysis, heavy export/media, and the offer pipeline. A single shared
queue lets slow jobs starve fast ones, and naive workers double-process on retries, crashes, or duplicate
delivery.

## Decision
Separate processing **lanes** (analysis / heavy export-media / offer), each with its own concurrency limit
and lease reaper. Every job is idempotent and crash-safe, protected by:
- **lease fencing** (`lease_version`) so a stale worker cannot overwrite a newer one,
- **poison-job detection** (bounded repeated identical failures),
- **bounded retry backoff**, and
- **crash-safe AI budget reservations** swept after `kill -9`.

(Constitution Art. 5 & 8; Invariants INV-006, INV-007.)

## Consequences
- **+** Fast lane never blocked by heavy jobs; safe under retries, leases, crashes, duplicate delivery.
- **−** More moving parts (multiple queues, reapers, sweeper) to operate and monitor.

## Alternatives considered
- **Single queue, at-most-once** — rejected: head-of-line blocking and data loss on crash.
