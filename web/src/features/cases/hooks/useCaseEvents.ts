/**
 * SSE hook for real-time case activity updates.
 *
 * Connects to GET /cases/{caseId}/activity/stream, parses canonical events,
 * and calls onEvent for each received message.
 *
 * Reconnect behaviour:
 *   - Uses Last-Event-ID header to replay any missed events after reconnect.
 *   - Exponential back-off: 1s → 2s → 4s → 8s → 16s (cap).
 *   - Heartbeat watchdog: if no bytes arrive for 60s the stream is assumed
 *     stale and a fresh connection is opened (server heartbeats every 30s).
 *   - Online/offline: when the browser regains network connectivity the hook
 *     immediately reconnects without waiting for the back-off timer.
 *   - Does NOT reconnect when the component unmounts or caseId changes.
 *
 * Authentication:
 *   Uses Fetch API with Authorization header (not native EventSource, which
 *   does not support custom headers).  On 401, stops reconnecting — caller
 *   should redirect to login via the standard logout flow.
 */
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { tokenStorage } from 'shared/lib/apiClient'
import { isCaseEvent, type CaseEvent } from 'shared/types/events.types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const MAX_BACKOFF_MS = 16_000
const INITIAL_BACKOFF_MS = 1_000
// Must be greater than 2× heartbeat interval (server sends every 30s).
const STALE_STREAM_TIMEOUT_MS = 60_000

export type CaseEventsOptions = {
  /** Called for each successfully parsed canonical CaseEvent. */
  onEvent: (event: CaseEvent) => void
  /** Called when the SSE connection drops and will be retried. */
  onReconnecting?: (attempt: number) => void
  /** Called when reconnect is abandoned (e.g. 401 / component unmounted). */
  onAbandoned?: (reason: string) => void
}

export function useCaseEvents(caseId: string, opts: CaseEventsOptions): void {
  const optsRef = useRef(opts)
  optsRef.current = opts

  // Incremented by the `online` event handler to force an immediate reconnect
  // (bypasses back-off by triggering a new useEffect run with a fresh controller).
  const [reconnectEpoch, triggerReconnect] = useReducer((n: number) => n + 1, 0)

  const startConnection = useCallback(
    async (
      abortSignal: AbortSignal,
      lastSeqRef: { current: number | null },
      backoffRef: { current: number },
      attemptRef: { current: number },
    ) => {
      // Stable across reconnects within this session so replayed events are
      // not dispatched a second time (seenIds was previously reset per stream,
      // which allowed a stale analysis_result_id to be re-stamped into cache
      // if a replay delivered an older analysis.completed event after a newer
      // one had already been processed).
      const seenIds = new Set<string>()

      while (!abortSignal.aborted) {
        const token = tokenStorage.getAccess()
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
        }
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (lastSeqRef.current !== null) {
          headers['Last-Event-ID'] = String(lastSeqRef.current)
        }

        let response: Response
        try {
          response = await fetch(`${API_BASE}/cases/${caseId}/activity/stream`, {
            headers,
            signal: abortSignal,
          })
        } catch (err) {
          if (abortSignal.aborted) return
          await _backoff(backoffRef, abortSignal)
          continue
        }

        if (response.status === 401) {
          optsRef.current.onAbandoned?.('unauthorized')
          return
        }

        if (!response.ok || !response.body) {
          await _backoff(backoffRef, abortSignal)
          continue
        }

        // Stream connected — reset back-off.
        backoffRef.current = INITIAL_BACKOFF_MS
        attemptRef.current = 0

        await _readStream(response.body, abortSignal, lastSeqRef, optsRef, seenIds)

        if (abortSignal.aborted) return

        // Stream ended without abort — reconnect.
        optsRef.current.onReconnecting?.(++attemptRef.current)
        await _backoff(backoffRef, abortSignal)
      }
    },
    [caseId],
  )

  useEffect(() => {
    if (!caseId) return
    const controller = new AbortController()
    const lastSeqRef: { current: number | null } = { current: null }
    const backoffRef: { current: number } = { current: INITIAL_BACKOFF_MS }
    const attemptRef: { current: number } = { current: 0 }

    startConnection(controller.signal, lastSeqRef, backoffRef, attemptRef).catch(() => {
      // Swallow — abort errors are expected on unmount.
    })

    // When the browser regains network connectivity, abort the current
    // connection immediately so the next reconnect attempt happens without
    // waiting for the back-off timer.  triggerReconnect() increments
    // reconnectEpoch which re-runs this effect with a fresh AbortController.
    const handleOnline = () => triggerReconnect()
    window.addEventListener('online', handleOnline)

    return () => {
      controller.abort()
      window.removeEventListener('online', handleOnline)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, startConnection, reconnectEpoch])
}

// ---------------------------------------------------------------------------
// SSE stream parser
// ---------------------------------------------------------------------------

async function _readStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  lastSeqRef: { current: number | null },
  optsRef: { current: CaseEventsOptions },
  seenIds: Set<string>,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (!signal.aborted) {
      // Race the read against a stale-stream watchdog.  If the server stops
      // sending (including heartbeats) for STALE_STREAM_TIMEOUT_MS the
      // watchdog resolves first and we break out to trigger a reconnect.
      const staleError = new Error('stale')
      let staleTimer: ReturnType<typeof setTimeout> | undefined
      const stalePromise = new Promise<never>((_, reject) => {
        staleTimer = setTimeout(() => reject(staleError), STALE_STREAM_TIMEOUT_MS)
        signal.addEventListener('abort', () => { clearTimeout(staleTimer); reject(staleError) }, { once: true })
      })

      let done: boolean
      let value: Uint8Array | undefined
      try {
        ;({ done, value } = await Promise.race([reader.read(), stalePromise]))
      } catch (err) {
        clearTimeout(staleTimer)
        break  // stale or aborted — outer loop will reconnect
      }
      clearTimeout(staleTimer)

      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() ?? ''

      for (const block of events) {
        if (!block.trim()) continue

        let dataLine = ''
        let idLine = ''

        for (const line of block.split('\n')) {
          if (line.startsWith('data:')) {
            dataLine = line.slice(5).trim()
          } else if (line.startsWith('id:')) {
            idLine = line.slice(3).trim()
          }
          // ':' comments (heartbeat) are ignored
        }

        // Advance Last-Event-ID only when seq is present (outbox frames).
        if (idLine) {
          const seq = parseInt(idLine, 10)
          if (!isNaN(seq)) {
            lastSeqRef.current = seq
          }
        }

        if (!dataLine) continue

        let parsed: unknown
        try {
          parsed = JSON.parse(dataLine)
        } catch {
          continue
        }

        if (!isCaseEvent(parsed)) continue

        // Deduplicate by event_id — handles both live and outbox paths.
        if (seenIds.has(parsed.event_id)) continue
        seenIds.add(parsed.event_id)

        optsRef.current.onEvent(parsed)
      }
    }
  } finally {
    reader.cancel().catch(() => undefined)
  }
}

async function _backoff(
  backoffRef: { current: number },
  signal: AbortSignal,
): Promise<void> {
  const delay = backoffRef.current
  backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS)
  await new Promise<void>((resolve) => {
    const id = setTimeout(resolve, delay)
    signal.addEventListener('abort', () => {
      clearTimeout(id)
      resolve()
    }, { once: true })
  })
}
