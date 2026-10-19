import { Link, Outlet, useParams } from '@tanstack/react-router'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  CasePhaseIndicator,
  CaseStatusBadge,
  CaseWorkspaceProvider,
  CaseWorkflowActions,
  useCaseDetail,
} from 'features/cases'
import { useCaseEvents } from 'features/cases/hooks/useCaseEvents'
import { CASE_KEYS } from 'features/cases/api/caseQueries'
import { WORK_CATALOG_KEYS } from 'features/work-catalog/api/workCatalogQueries'
import type { AnalysisCompletedPayload, CaseEvent } from 'shared/types/events.types'
import type { CaseDetail } from 'features/cases/types/case.types'

const CASE_NAV = [
  { label: 'Overview', to: '/cases/$caseId' },
  { label: 'Photos', to: '/cases/$caseId/photos' },
  { label: 'Work Items', to: '/cases/$caseId/work-items' },
  { label: 'Estimates', to: '/cases/$caseId/estimates' },
  { label: 'Exports', to: '/cases/$caseId/exports' },
  { label: 'Timeline', to: '/cases/$caseId/timeline' },
] as const

type ConnectionStatus = 'connected' | 'reconnecting' | 'abandoned'

export function CaseLayout() {
  const { caseId } = useParams({ strict: false })
  const { data: caseDetail, isLoading, isError } = useCaseDetail(caseId ?? '')
  const queryClient = useQueryClient()
  const [connStatus, setConnStatus] = useState<ConnectionStatus>('connected')
  const [proposalRecalculating, setProposalRecalculating] = useState(false)

  useCaseEvents(caseId ?? '', {
    onEvent(event: CaseEvent) {
      // Any incoming event means the stream is alive — clear reconnecting state.
      setConnStatus('connected')

      switch (event.event_type) {
        case 'analysis.started':
          void queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(event.aggregate_id) })
          break

        case 'analysis.completed': {
          // Optimistic update: stamp the new referencePhotoId into the cached
          // CaseDetail immediately so the overlay guard in PhotoViewerPage is
          // correct from the first render, before the full refetch returns.
          // This closes the stale-cache window between invalidation and refetch.
          //
          // Guard: only stamp when the incoming ID is different from what is
          // already cached.  seenIds (lifted in useCaseEvents) prevents most
          // replay re-delivery, but this check is a second line of defence —
          // it prevents a replayed older event from rolling the cache back to a
          // stale analysis_result_id if it somehow slips through deduplication.
          const acPayload = event.payload as AnalysisCompletedPayload
          if (acPayload.analysis_result_id && acPayload.reference_photo_id) {
            const cached = queryClient.getQueryData<CaseDetail>(
              CASE_KEYS.detail(event.aggregate_id),
            )
            if (cached && cached.latestAnalysis?.id !== acPayload.analysis_result_id) {
              queryClient.setQueryData<CaseDetail>(CASE_KEYS.detail(event.aggregate_id), {
                ...cached,
                latestAnalysis: cached.latestAnalysis
                  ? {
                      ...cached.latestAnalysis,
                      id: acPayload.analysis_result_id,
                      referencePhotoId: acPayload.reference_photo_id,
                    }
                  : cached.latestAnalysis,
              })
            }
          }
          // Full refetch: processingStatus / isAnalysisReference may have changed.
          void queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(event.aggregate_id) })
          void queryClient.invalidateQueries({ queryKey: CASE_KEYS.photos(event.aggregate_id) })
          break
        }

        case 'proposal.recalculate.started':
          setProposalRecalculating(true)
          break

        case 'proposal.ready':
          setProposalRecalculating(false)
          void queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(event.aggregate_id) })
          void queryClient.invalidateQueries({
            queryKey: WORK_CATALOG_KEYS.caseItems(event.aggregate_id),
          })
          break

        default:
          break
      }
    },
    onReconnecting() {
      setConnStatus('reconnecting')
    },
    onAbandoned() {
      setConnStatus('abandoned')
    },
  })

  if (!caseId) {
    return null
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
          <div className="h-5 w-40 animate-pulse rounded bg-slate-200" />
          <div className="mt-3 h-8 w-64 animate-pulse rounded bg-slate-100" />
          <div className="mt-6 h-24 animate-pulse rounded-3xl bg-slate-100" />
        </section>
        <Outlet />
      </div>
    )
  }

  if (isError || !caseDetail) {
    return (
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-red-100 bg-red-50 p-6">
          <p className="text-sm text-red-600">Failed to load case workspace.</p>
        </section>
        <Outlet />
      </div>
    )
  }

  return (
    <CaseWorkspaceProvider caseDetail={caseDetail}>
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600">
                  Case workspace
                </p>
                <CaseStatusBadge status={caseDetail.status} />
              </div>

              <h1 className="mt-3 truncate text-3xl font-semibold text-slate-950">
                {caseDetail.title}
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                {caseDetail.description ?? 'Workflow, work types and delivery actions are scoped to this case phase.'}
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                {CASE_NAV.map((item) => (
                  <Link
                    key={item.label}
                    to={item.to}
                    params={{ caseId }}
                    activeProps={{
                      className: 'border-emerald-300 bg-emerald-50 text-emerald-800',
                    }}
                    inactiveProps={{
                      className: 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
                    }}
                    className="rounded-full border px-4 py-2 text-sm font-medium transition"
                  >
                    {item.label}
                  </Link>
                ))}
                <ConnectionBadge status={connStatus} />
                {proposalRecalculating && <ProposalRecalculatingBadge />}
              </div>
            </div>

            <div className="w-full max-w-xl space-y-4 xl:w-[28rem]">
              <CasePhaseIndicator status={caseDetail.status} />
              <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  Workflow actions
                </p>
                <div className="mt-4">
                  <CaseWorkflowActions
                    caseId={caseDetail.id}
                    status={caseDetail.status}
                    availableTransitions={caseDetail.availableTransitions}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <Outlet />
      </div>
    </CaseWorkspaceProvider>
  )
}

function ProposalRecalculatingBadge() {
  return (
    <span className="flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-700">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-violet-400" />
      Proposal updating…
    </span>
  )
}

function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  if (status === 'connected') return null

  if (status === 'reconnecting') {
    return (
      <span className="flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
        Syncing…
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700">
      <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
      Live updates paused —{' '}
      <button
        type="button"
        className="underline underline-offset-2 hover:text-red-900"
        onClick={() => window.location.reload()}
      >
        refresh
      </button>
    </span>
  )
}
