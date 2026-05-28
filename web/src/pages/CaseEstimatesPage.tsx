import { useState } from 'react'
import { useParams } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { CASE_KEYS, useCaseDetail, useCaseTimeline } from 'features/cases'
import type { ProposalInputVersions } from 'features/cases'
import { useToast } from 'app/providers/ToastProvider'
import type { CaseTimelineEvent } from 'features/cases/api/caseApi'

// ---------------------------------------------------------------------------
// ProposalStaleNotice — shown when PATCH /proposal-draft returns 409 PROPOSAL_STALE
// ---------------------------------------------------------------------------

interface ProposalStaleState {
  serverVersion: number
  localChanges: Record<string, unknown>
}

function ProposalStaleNotice({
  notice,
  onReload,
}: {
  notice: ProposalStaleState
  onReload: () => void
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-amber-900">
          Proposal has been updated
        </p>
        <p className="mt-0.5 text-xs text-amber-700">
          Someone else saved a newer version (v{notice.serverVersion}). Your local changes are
          preserved below but cannot be saved until you reload.
        </p>
      </div>
      <button
        type="button"
        className="shrink-0 rounded-full bg-amber-100 px-3 py-1.5 text-xs font-semibold text-amber-900 transition hover:bg-amber-200"
        onClick={onReload}
      >
        Discard &amp; reload
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// MeasurementTimeline
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
  const d = new Date(iso)
  return d.toLocaleString('cs-CZ', { dateStyle: 'short', timeStyle: 'short' })
}

type TimelineFilter = 'all' | 'ai' | 'pricing' | 'user' | 'system'

const FILTER_EVENT_TYPES: Record<TimelineFilter, ReadonlySet<string>> = {
  all:     new Set(),
  ai:      new Set(['analysis.started', 'analysis.completed']),
  pricing: new Set(['proposal.recalculate.started', 'proposal.ready', 'quote.ready']),
  user:    new Set(['measurement.confirmed']),
  system:  new Set(['case.created', 'export.completed']),
}

const FILTER_CHIPS: { id: TimelineFilter; label: string; activeClass: string }[] = [
  { id: 'all',     label: 'Vše',     activeClass: 'bg-slate-800 text-white' },
  { id: 'ai',      label: 'AI',      activeClass: 'bg-violet-600 text-white' },
  { id: 'pricing', label: 'Ceník',   activeClass: 'bg-emerald-600 text-white' },
  { id: 'user',    label: 'Uživatel', activeClass: 'bg-blue-600 text-white' },
  { id: 'system',  label: 'Systém',  activeClass: 'bg-slate-500 text-white' },
]

function MeasurementTimeline({ events }: { events: CaseTimelineEvent[] }) {
  const [filter, setFilter] = useState<TimelineFilter>('all')

  const visible = filter === 'all'
    ? events
    : events.filter((e) => FILTER_EVENT_TYPES[filter].has(e.eventType))

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
          Historie měření
        </p>
        <div className="flex flex-wrap gap-1.5">
          {FILTER_CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => setFilter(chip.id)}
              className={[
                'rounded-full px-3 py-1 text-xs font-medium transition',
                filter === chip.id
                  ? chip.activeClass
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              ].join(' ')}
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="text-sm text-slate-400">Žádné události v této kategorii.</p>
      ) : (
        <ol className="relative border-l border-slate-200 pl-5 space-y-4">
          {visible.map((evt, i) => (
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

// ---------------------------------------------------------------------------
// ProposalProvenancePanel — P2: shows which versions generated this proposal
// ---------------------------------------------------------------------------

function ProposalProvenancePanel({ versions }: { versions: ProposalInputVersions }) {
  const snap = versions.pricingProfileSnapshot
  return (
    <div className="rounded-2xl border border-violet-100 bg-violet-50/60 p-5">
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-violet-600">
        Vstupní verze kalkulace
      </p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-3">
        {versions.analysisProfileCode && (
          <>
            <dt className="text-slate-500">AI profil</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {versions.analysisProfileCode}
              {versions.analysisProfileVersion != null && (
                <span className="ml-1 text-slate-400">v{versions.analysisProfileVersion}</span>
              )}
            </dd>
          </>
        )}
        {versions.catalogPricingProfileCode && (
          <>
            <dt className="text-slate-500">Ceník profil</dt>
            <dd className="col-span-2 font-medium text-slate-800">
              {versions.catalogPricingProfileCode}
              {versions.catalogPricingProfileVersion != null && (
                <span className="ml-1 text-slate-400">v{versions.catalogPricingProfileVersion}</span>
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
      </dl>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function CaseEstimatesPage() {
  const { caseId } = useParams({ strict: false })
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [staleNotice, setStaleNotice] = useState<ProposalStaleState | null>(null)

  const { data: caseDetail } = useCaseDetail(caseId ?? '')
  const { data: timelineEvents, isLoading: isTimelineLoading } = useCaseTimeline(caseId ?? '')

  function handleReload() {
    setStaleNotice(null)
    if (caseId) {
      queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(caseId) })
    }
    toast.info('Proposal reloaded.')
  }

  const hasTimeline = (timelineEvents?.length ?? 0) > 0
  const inputVersions = caseDetail?.finalProposal?.inputVersions ?? null

  return (
    <section className="space-y-4">
      {staleNotice && (
        <ProposalStaleNotice notice={staleNotice} onReload={handleReload} />
      )}

      {/* Measurement history timeline */}
      {isTimelineLoading ? (
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
          <div className="space-y-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="flex gap-3">
                <div className="h-6 w-6 animate-pulse rounded-full bg-slate-200" />
                <div className="h-4 flex-1 animate-pulse rounded bg-slate-100" />
              </div>
            ))}
          </div>
        </div>
      ) : hasTimeline ? (
        <MeasurementTimeline events={timelineEvents!} />
      ) : (
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
            Historie měření
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Zatím žádné události. Spusťte analýzu pro zobrazení historie.
          </p>
        </div>
      )}

      {/* Proposal provenance panel — only when a final proposal exists */}
      {inputVersions && <ProposalProvenancePanel versions={inputVersions} />}
    </section>
  )
}
