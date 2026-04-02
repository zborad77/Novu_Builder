# Operational Load Rehearsal

Script: [run-operational-load-rehearsal.py](d:/Novu_Hub/Novu_Builder/scripts/run-operational-load-rehearsal.py)

## Goal

Prove operational truth, not a pretty benchmark:

- API burst behavior
- queue throughput and drain behavior
- bounded retry behavior
- tenant fairness signals
- short sustained load behavior

## Preconditions

- backend reachable on `http://127.0.0.1:8000`
- manager tenant credentials available
- optional superadmin credentials for `/api/v1/health/internal`
- Redis + worker must be healthy if queue scenarios should count as valid
- for retry storm probe use `AI_ANALYSIS_PROVIDER=mock`

If `GET /api/v1/ready/processing?strict=true` is not green, the script marks queue phases as blocked and keeps that separate from API results.

## Tenant Config

Optional JSON file:

```json
{
  "tenants": [
    { "label": "tenant-a", "email": "demo@novu.local", "password": "demo1234" },
    { "label": "tenant-b", "email": "load-b@novu.local", "password": "LoadB1234!" }
  ]
}
```

Without `--tenant-file`, the script uses the default demo tenant.

## Recommended Run

```powershell
& .\python-backend\.venv\Scripts\python.exe .\scripts\run-operational-load-rehearsal.py `
  --base-url http://127.0.0.1:8000 `
  --tenant-file .\artifacts\load-tenants.json `
  --observer-email admin@novu.cz `
  --observer-password NovuAdmin2024! `
  --json-out .\artifacts\operational-load-rehearsal.json
```

## What The Script Produces

- `preflight`
- `authBurst`
- `crudPhotoBurst`
- `queueThroughput`
- `retryStorm`
- `tenantFairness`
- `sustainedLoad`
- per-bucket latency summaries
- explicit blocker classification
- pilot / medium / 100k posture summary

## Known Gaps

The rehearsal can read queue, retry, DLQ and backlog-age signals from the backend diagnostics, but it still cannot prove:

- host CPU saturation
- host memory growth
- direct PostgreSQL connection pressure
- direct Redis server pressure

Those require node/runtime telemetry outside the HTTP diagnostics path.
