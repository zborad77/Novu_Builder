# Case Activity WebSocket Contract

This document defines the backend payload contract for desktop case activity streaming.

## Goals

- Keep the transport boundary explicit before implementing the WebSocket endpoint.
- Preserve desktop layering:
  - `CaseActivityService` is the event source.
- `CaseDetailViewModel` maps raw events to UI behavior.
- `CaseDetailView` only redraws.

## Endpoint

- Path: `/api/v1/ws/case-activity`
- Auth: access token in query string, `?token=<jwt>`
- Lifecycle:
  - desktop connects after login
  - desktop sends `subscribe` / `unsubscribe` commands
  - backend streams only typed case-activity events

## Client Commands

### `subscribe`

```json
{
  "type": "subscribe",
  "caseId": "case_123",
  "jobId": "job_123"
}
```

- `caseId` is required
- `jobId` is optional
- backend validates tenant access and that `jobId` belongs to `caseId`

### `unsubscribe`

```json
{
  "type": "unsubscribe"
}
```

## Snapshot Semantics

- After a valid `subscribe`, backend immediately emits the current snapshot as normal events.
- For jobs:
  - current non-terminal state emits `job_status_changed`
  - current terminal state emits `job_completed`
- For images:
  - backend emits one `image_status_changed` per image currently known in the case
- After the initial snapshot, backend emits only diffs.

## Event Envelope

Every event must contain:

- `type`
- `caseId`
- `timestamp`

`timestamp` must be an ISO 8601 UTC datetime string.

## Event Types

### `job_status_changed`

Emitted when an analysis job is currently in a non-terminal state and that state changed since the last snapshot.

```json
{
  "type": "job_status_changed",
  "caseId": "case_123",
  "jobId": "job_123",
  "status": "running",
  "timestamp": "2026-04-20T12:30:45Z"
}
```

Allowed `status` values:

- `queued`
- `running`
- `completed`
- `failed`
- `canceled`
- `dead_letter`

### `job_completed`

Emitted when a job is currently in a terminal state and that state changed since the last snapshot.

```json
{
  "type": "job_completed",
  "caseId": "case_123",
  "jobId": "job_123",
  "status": "completed",
  "timestamp": "2026-04-20T12:31:10Z"
}
```

Allowed terminal `status` values:

- `completed`
- `failed`
- `canceled`
- `dead_letter`

### `image_status_changed`

Emitted when a case image processing state changed since the last snapshot.

```json
{
  "type": "image_status_changed",
  "caseId": "case_123",
  "imageId": "img_123",
  "jobId": "job_123",
  "status": "processing",
  "timestamp": "2026-04-20T12:32:00Z"
}
```

Allowed `status` values:

- `uploaded`
- `processing`
- `ready`
- `failed`

`jobId` is optional for image events because image processing may be correlated with an analysis flow, but that relationship is not guaranteed for every producer.

## Fail-Fast Rules

- Unknown command types are invalid.
- Unknown command fields are invalid.
- Unknown event types are invalid.
- Unknown fields are invalid.
- Missing required IDs are invalid.
- `job_completed.status` must be terminal; `running` is invalid.
- `subscribe` must fail fast if the case does not exist in tenant scope or the job does not belong to the subscribed case.
- The backend must validate commands and payloads against the typed contract before using or sending them.

## Backend Schema Source Of Truth

Typed models live in:

- `python-backend/app/schemas/case_activity.py`

These models should be reused by the future WebSocket route and any internal publisher code.
