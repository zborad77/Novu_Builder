# Pilot Load Rehearsal

This is a small, practical rehearsal for pilot readiness. It is not a large-scale performance program.

## Goal

Verify that a pilot-sized load does not break:

- auth flow
- case/photo flow
- analysis queue orchestration
- worker drain behavior
- basic operational visibility

## Preconditions

Use mock AI provider for rehearsal:

- `AI_ANALYSIS_PROVIDER=mock`

Recommended runtime shape:

- backend available on `http://localhost:8000`
- manager user for normal flows
- optional superadmin user for `/api/v1/health/internal`
- Redis and worker available if queue/worker phase should be considered valid

If `GET /api/v1/ready/processing?strict=true` returns `jobProcessingReady=false`, treat queue/worker verification as blocked by environment, not as a green run.

## What The Script Runs

Script: [run-pilot-load-rehearsal.py](d:/Novu_Hub/Novu_Builder/scripts/run-pilot-load-rehearsal.py)

Phases:

1. Auth burst
   - concurrent `POST /auth/login`
   - concurrent `POST /auth/refresh`
2. Project/photo burst
   - `POST /cases`
   - `POST /cases/{id}/images`
   - `GET /images/{id}/preview`
3. Queue/worker orchestration
   - `POST /cases/{id}/analysis-jobs`
   - poll `GET /analysis-jobs/{job_id}`
   - sample `GET /ready/processing?strict=true`
   - optional `GET /health/internal` with superadmin observer
   - controlled cancel/retry probe on a small sample
4. End-to-end mini flow
   - smaller mixed create/upload/analyze path

## Recommended Pilot Run

Order:

1. Start backend, Redis, worker
2. Confirm `GET /api/v1/health` is `ok`
3. Confirm `GET /api/v1/ready/processing?strict=true` is ready
4. Run rehearsal
5. Read JSON summary and observer samples

Suggested command:

```powershell
& .\python-backend\.venv\Scripts\python.exe .\scripts\run-pilot-load-rehearsal.py `
  --base-url http://localhost:8000 `
  --email demo@novu.local `
  --password demo1234 `
  --observer-email admin@novu.cz `
  --observer-password NovuAdmin2024! `
  --json-out .\artifacts\pilot-load-rehearsal.json
```

Suggested duration:

- auth burst: under 1 minute
- project/photo burst: 1-3 minutes
- queue/worker burst with polling: 2-5 minutes
- end-to-end mini flow: 1-3 minutes
- whole rehearsal: usually under 10 minutes

## Small Pilot Load Shape

Default shape in the script:

- `20` auth login+refresh pairs
- `24` cases
- `1` photo per case
- `24` analysis jobs on distinct cases
- `6` mixed end-to-end flows

This is enough to expose obvious pilot blockers without wasting provider budget or pretending to test 100+ tenant scale.

## Metrics To Watch

Primary:

- auth login p95
- refresh p95
- case create p95
- image upload p95
- preview p95
- analysis enqueue p95
- terminal job completion ratio
- completed job ratio
- observed queue length peak
- observed jobs queued / running peak
- worker state and queue state during the run

Operational warning signs:

- `queueState=unavailable`
- `workerState=unknown`, `missing`, or `stale`
- queue depth rises and does not drain
- jobs remain `queued` past timeout
- request error rate above 2%
- upload or auth p95 spikes above thresholds

## Success Criteria

The script evaluates these default criteria:

- auth login p95 `<= 1000 ms`
- auth refresh p95 `<= 1000 ms`
- create case p95 `<= 1200 ms`
- image upload p95 `<= 2200 ms`
- preview p95 `<= 750 ms`
- analysis enqueue p95 `<= 1200 ms`
- HTTP error rate `<= 2%`
- at least `95%` of queued jobs reach a terminal state within timeout
- at least `90%` of queued jobs complete successfully

## How To Read The Verdict

- `pilot_ready`
  - all configured criteria passed
- `pilot_possible_with_watchouts`
  - mostly healthy, but one or more thresholds missed
- `not_pilot_ready`
  - meaningful instability or too many jobs did not complete
- `blocked_by_environment`
  - queue/worker proof is missing because runtime conditions were not present

## What Is Acceptable For Pilot Vs 100+ Tenants

Acceptable for pilot:

- short auth and upload bursts remain responsive
- queue drains a few dozen mock jobs cleanly
- worker stays alive
- no sustained backlog after the burst

Not acceptable for 100+ tenants:

- queue/worker proof missing
- queue backlog sticks after the burst
- repeated 429/5xx during a small rehearsal
- jobs need manual recovery after a few dozen submissions

This rehearsal is intentionally small. If pilot volume is higher than this by design, raise the job count and case count only after the small baseline is green.
