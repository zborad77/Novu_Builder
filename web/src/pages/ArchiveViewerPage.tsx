import { useState, useCallback, useRef } from 'react'
import { unzipSync } from 'fflate'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ManifestData {
  archiveSchemaVersion: number
  generatorVersion: string
  generatedAt: string
  files: Record<string, string>
}

interface ProposalSnapshot {
  archiveSchemaVersion: number
  id: string
  status: string
  draftVersion: number
  analysisResultId: string | null
  inputVersions: {
    analysisProfileCode: string | null
    analysisProfileVersion: number | null
    catalogPricingProfileCode: string | null
    catalogPricingProfileVersion: number | null
    pricingProfileSnapshot: {
      hourlyRate: number
      marginStandardPct: number
      vatPct: number
      currency: string
    } | null
  } | null
}

interface TimelineEvent {
  seq?: number
  eventType: string
  label: string
  occurredAt: string | null
  payload: Record<string, unknown>
}

interface ParsedArchive {
  fileName: string
  manifest: ManifestData | null
  proposal: ProposalSnapshot | null
  timelineEvents: TimelineEvent[]
  pricingSnapshot: Record<string, unknown> | null
  integrityStatus: 'ok' | 'warning' | 'error'
  messages: string[]
}

// ---------------------------------------------------------------------------
// Archive parsing
// ---------------------------------------------------------------------------

async function sha256Hex(data: Uint8Array): Promise<string> {
  // .slice() always returns ArrayBuffer, satisfying crypto.subtle.digest's type
  const copy = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer
  const buf = await crypto.subtle.digest('SHA-256', copy)
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

async function parseArchive(file: File): Promise<ParsedArchive> {
  const arrayBuf = await file.arrayBuffer()
  let files: Record<string, Uint8Array>
  try {
    files = unzipSync(new Uint8Array(arrayBuf))
  } catch (e) {
    return {
      fileName: file.name,
      manifest: null,
      proposal: null,
      timelineEvents: [],
      pricingSnapshot: null,
      integrityStatus: 'error',
      messages: [`Not a valid ZIP file: ${e instanceof Error ? e.message : String(e)}`],
    }
  }

  const dec = new TextDecoder()
  const messages: string[] = []
  let integrityStatus: 'ok' | 'warning' | 'error' = 'ok'

  function parseJson<T>(name: string): T | null {
    if (!(name in files)) return null
    try {
      return JSON.parse(dec.decode(files[name])) as T
    } catch {
      messages.push(`${name}: invalid JSON`)
      integrityStatus = 'error'
      return null
    }
  }

  const manifest = parseJson<ManifestData>('manifest.json')
  const proposal = parseJson<ProposalSnapshot>('proposal_snapshot.json')
  const timelineRaw = parseJson<{ archiveSchemaVersion: number; events: TimelineEvent[] } | TimelineEvent[]>('timeline.json')
  const pricingSnapshot = parseJson<Record<string, unknown>>('pricing_snapshot.json')

  // Required files check
  for (const req of ['proposal_snapshot.json', 'timeline.json'] as const) {
    if (!(req in files)) {
      messages.push(`Missing required file: ${req}`)
      integrityStatus = 'error'
    }
  }

  // Timeline envelope check
  let timelineEvents: TimelineEvent[] = []
  if (timelineRaw !== null) {
    if (Array.isArray(timelineRaw)) {
      messages.push('timeline.json: pre-versioning format (raw list) — open with matching viewer version')
      integrityStatus = 'warning'
      timelineEvents = timelineRaw
    } else if (typeof timelineRaw === 'object') {
      timelineEvents = timelineRaw.events ?? []
    }
  }

  // Manifest hash verification
  if (manifest?.files) {
    for (const [fname, expected] of Object.entries(manifest.files)) {
      if (typeof expected !== 'string' || !expected.startsWith('sha256:')) continue
      if (!(fname in files)) {
        messages.push(`Manifest references missing file: ${fname}`)
        integrityStatus = 'error'
        continue
      }
      const actualHex = await sha256Hex(files[fname]!)
      const expectedHex = expected.slice('sha256:'.length)
      if (actualHex !== expectedHex) {
        messages.push(`Integrity check failed: ${fname} — file may have been tampered`)
        integrityStatus = 'error'
      }
    }
  } else {
    messages.push('manifest.json absent — file integrity cannot be verified')
    if (integrityStatus === 'ok') integrityStatus = 'warning'
  }

  return {
    fileName: file.name,
    manifest,
    proposal,
    timelineEvents,
    pricingSnapshot,
    integrityStatus,
    messages,
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const EVENT_ICONS: Record<string, string> = {
  'case.created':                 '📁',
  'analysis.started':             '🔍',
  'analysis.completed':           '🤖',
  'measurement.confirmed':        '✅',
  'proposal.recalculate.started': '⚙️',
  'proposal.ready':               '📋',
  'quote.ready':                  '💰',
  'export.completed':             '📄',
}

function formatOccurredAt(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('cs-CZ', { dateStyle: 'short', timeStyle: 'short' })
}

function IntegrityBadge({ status }: { status: 'ok' | 'warning' | 'error' }) {
  if (status === 'ok') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
        ✓ Verified
      </span>
    )
  }
  if (status === 'warning') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
        ⚠ Warning
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800">
      ✗ Integrity error
    </span>
  )
}

function ArchiveHeader({ archive, onClose }: { archive: ParsedArchive; onClose: () => void }) {
  const { manifest, integrityStatus, messages, fileName } = archive
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-800">{fileName}</p>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {manifest?.generatedAt && (
              <span>Generated: {formatOccurredAt(manifest.generatedAt)}</span>
            )}
            {manifest?.generatorVersion && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">
                {manifest.generatorVersion}
              </span>
            )}
            {manifest?.archiveSchemaVersion != null && (
              <span className="text-slate-400">schema v{manifest.archiveSchemaVersion}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <IntegrityBadge status={integrityStatus} />
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close archive"
          >
            ✕
          </button>
        </div>
      </div>
      {messages.length > 0 && (
        <ul className="mt-3 space-y-1">
          {messages.map((msg, i) => (
            <li key={i} className={[
              'text-xs',
              integrityStatus === 'error' ? 'text-red-700' : 'text-amber-700',
            ].join(' ')}>
              {msg}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function OfflineTimeline({ events }: { events: TimelineEvent[] }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
      <p className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
        Historie měření
      </p>
      {events.length === 0 ? (
        <p className="text-sm text-slate-400">Žádné události v archivu.</p>
      ) : (
        <ol className="relative border-l border-slate-200 pl-5 space-y-4">
          {events.map((evt, i) => (
            <li key={evt.seq ?? `${evt.eventType}-${i}`} className="relative">
              <span className="absolute -left-[1.35rem] flex h-6 w-6 items-center justify-center rounded-full bg-white text-sm ring-2 ring-slate-200">
                {EVENT_ICONS[evt.eventType] ?? '•'}
              </span>
              <div className="flex items-baseline justify-between gap-4">
                <p className="text-sm font-medium text-slate-800">{evt.label}</p>
                <time className="shrink-0 text-xs text-slate-400">
                  {formatOccurredAt(evt.occurredAt)}
                </time>
              </div>
              {evt.eventType === 'measurement.confirmed' && evt.payload.manual_area_sqm != null && (
                <p className="mt-0.5 text-xs text-emerald-700">
                  {Number(evt.payload.manual_area_sqm).toFixed(1)} m²
                </p>
              )}
              {evt.eventType === 'analysis.completed' && evt.payload.estimated_area_sqm != null && (
                <p className="mt-0.5 text-xs text-violet-700">
                  AI odhad: {Number(evt.payload.estimated_area_sqm).toFixed(1)} m²
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function OfflineProvenance({ proposal }: { proposal: ProposalSnapshot }) {
  const iv = proposal.inputVersions
  const snap = iv?.pricingProfileSnapshot
  if (!iv) return null
  return (
    <div className="rounded-2xl border border-violet-100 bg-violet-50/60 p-5">
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-violet-600">
        Vstupní verze kalkulace
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
        {iv.analysisProfileCode && (
          <>
            <dt className="text-slate-500">AI profil</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {iv.analysisProfileCode}
              {iv.analysisProfileVersion != null && (
                <span className="ml-1 text-slate-400">v{iv.analysisProfileVersion}</span>
              )}
            </dd>
          </>
        )}
        {iv.catalogPricingProfileCode && (
          <>
            <dt className="text-slate-500">Ceník profil</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {iv.catalogPricingProfileCode}
              {iv.catalogPricingProfileVersion != null && (
                <span className="ml-1 text-slate-400">v{iv.catalogPricingProfileVersion}</span>
              )}
            </dd>
          </>
        )}
        {snap && (
          <>
            <dt className="text-slate-500">Hodinová sazba</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {snap.hourlyRate.toFixed(0)} {snap.currency}/h
            </dd>
            <dt className="text-slate-500">Marže (standard)</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {snap.marginStandardPct.toFixed(1)} %
            </dd>
            <dt className="text-slate-500">DPH</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {snap.vatPct.toFixed(0)} %
            </dd>
          </>
        )}
        <dt className="text-slate-500">Verze návrhu</dt>
        <dd className="col-span-2 font-medium text-slate-800">v{proposal.draftVersion}</dd>
        {proposal.analysisResultId && (
          <>
            <dt className="text-slate-500">Analysis ID</dt>
            <dd className="col-span-2 truncate font-mono text-[11px] text-slate-600">
              {proposal.analysisResultId}
            </dd>
          </>
        )}
      </dl>
    </div>
  )
}

function DropZone({ onFile }: { onFile: (f: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback((files: FileList | null) => {
    const f = files?.[0]
    if (f) onFile(f)
  }, [onFile])

  return (
    <div
      className={[
        'flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-16 transition',
        dragging
          ? 'border-violet-400 bg-violet-50'
          : 'border-slate-200 bg-white/60 hover:border-slate-300',
      ].join(' ')}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
    >
      <span className="text-5xl">📦</span>
      <div className="text-center">
        <p className="text-sm font-medium text-slate-700">Drop archive here</p>
        <p className="mt-0.5 text-xs text-slate-400">or click to select a proposal-archive-zip</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ArchiveViewerPage() {
  const [archive, setArchive] = useState<ParsedArchive | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleFile(file: File) {
    setLoading(true)
    try {
      const parsed = await parseArchive(file)
      setArchive(parsed)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <section className="space-y-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-8 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-violet-600" />
            <p className="text-sm text-slate-500">Parsing archive…</p>
          </div>
        </div>
      </section>
    )
  }

  if (!archive) {
    return (
      <section className="space-y-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Archive Viewer
          </p>
          <p className="mt-1 text-sm text-slate-400">
            Open a proposal archive ZIP offline — no backend required.
          </p>
        </div>
        <DropZone onFile={(f) => { void handleFile(f) }} />
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <ArchiveHeader archive={archive} onClose={() => setArchive(null)} />
      <OfflineTimeline events={archive.timelineEvents} />
      {archive.proposal && <OfflineProvenance proposal={archive.proposal} />}
    </section>
  )
}
