import { Link, Outlet, useParams } from '@tanstack/react-router'
import {
  CasePhaseIndicator,
  CaseStatusBadge,
  CaseWorkspaceProvider,
  CaseWorkflowActions,
  useCaseDetail,
} from 'features/cases'

const CASE_NAV = [
  { label: 'Overview', to: '/cases/$caseId' },
  { label: 'Photos', to: '/cases/$caseId/photos' },
  { label: 'Work Items', to: '/cases/$caseId/work-items' },
  { label: 'Estimates', to: '/cases/$caseId/estimates' },
  { label: 'Exports', to: '/cases/$caseId/exports' },
  { label: 'Timeline', to: '/cases/$caseId/timeline' },
] as const

export function CaseLayout() {
  const { caseId } = useParams({ strict: false })
  const { data: caseDetail, isLoading, isError } = useCaseDetail(caseId ?? '')

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

              <div className="mt-6 flex flex-wrap gap-3">
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
