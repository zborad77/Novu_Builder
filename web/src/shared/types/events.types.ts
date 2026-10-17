/**
 * Canonical SSE event shapes — mirrors python-backend/app/core/events.py.
 *
 * Every message received on a case or offer SSE stream conforms to one of
 * these types.  Use event_id for deduplication (stable across both the
 * live Redis path and the durable outbox path).  Use seq (when present)
 * as Last-Event-ID for reconnect replay.
 */

// ---------------------------------------------------------------------------
// Case events
// ---------------------------------------------------------------------------

export type CaseEventType =
  | 'analysis.started'
  | 'analysis.completed'
  | 'proposal.recalculate.started'
  | 'proposal.ready'
  | 'quote.ready'
  | 'export.completed'

/** Payload for analysis.started */
export interface AnalysisStartedPayload {
  status: 'analyzing'
}

/**
 * Payload for analysis.completed.
 *
 * analysis_result_id and reference_photo_id are present whenever the
 * analysis result was successfully persisted.  The web viewer uses them to
 * do an optimistic overlay update before the full refetch returns, avoiding
 * the stale-cache window where the guard would reject the overlay.
 *
 * Qt invariant: treat reference_photo_id as the canonical overlay anchor —
 * only display the maskPolygon on the photo whose id matches this field.
 */
export interface AnalysisCompletedPayload {
  status: 'analysis_completed'
  /** Stable identity of the stored AnalysisResult (e.g. "ana_abc12345"). */
  analysis_result_id: string | null
  /** The photo the AI ran against — overlay is only valid for this photo. */
  reference_photo_id: string | null
}

/** Payload for proposal.ready */
export interface ProposalReadyPayload {
  status: 'proposal_ready'
}

/** Union of all typed case event payloads.  Use a discriminated union on event_type. */
export type CaseEventPayload =
  | AnalysisStartedPayload
  | AnalysisCompletedPayload
  | ProposalReadyPayload
  | Record<string, unknown>

export interface CaseEvent {
  /** Monotonic sequence number from the outbox.  Absent on live-delivery frames.
   *  Use as Last-Event-ID on reconnect ONLY when present. */
  seq?: number
  /** Stable UUID = outbox_events.id.  Use for deduplication across both paths. */
  event_id: string
  event_type: CaseEventType
  aggregate_type: 'case'
  aggregate_id: string
  /** ISO-8601 UTC timestamp when the event was written to the outbox.
   *  Absent on live-delivery frames. */
  occurred_at?: string
  payload: CaseEventPayload
}

// ---------------------------------------------------------------------------
// Offer events
// ---------------------------------------------------------------------------

export type OfferStatus =
  | 'queued'
  | 'processing'
  | 'needs_more_info'
  | 'needs_review'
  | 'failed'
  | 'cancelled'
  | 'completed'

export interface OfferStatusChangedPayload {
  status: OfferStatus
  job_id: string | null
  [key: string]: unknown
}

export interface OfferEvent {
  seq?: number
  event_id: string
  event_type: 'offer.status_changed'
  aggregate_type: 'offer_request'
  aggregate_id: string
  occurred_at?: string
  payload: OfferStatusChangedPayload
}

// ---------------------------------------------------------------------------
// Type guard utilities
// ---------------------------------------------------------------------------

export function isCaseEvent(raw: unknown): raw is CaseEvent {
  if (typeof raw !== 'object' || raw === null) return false
  const r = raw as Record<string, unknown>
  return (
    typeof r['event_id'] === 'string' &&
    typeof r['event_type'] === 'string' &&
    r['aggregate_type'] === 'case'
  )
}

export function isOfferEvent(raw: unknown): raw is OfferEvent {
  if (typeof raw !== 'object' || raw === null) return false
  const r = raw as Record<string, unknown>
  return (
    typeof r['event_id'] === 'string' &&
    r['event_type'] === 'offer.status_changed' &&
    r['aggregate_type'] === 'offer_request'
  )
}
