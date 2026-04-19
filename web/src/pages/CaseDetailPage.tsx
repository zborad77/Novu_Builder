import { useParams } from '@tanstack/react-router'
import { useCaseDetail } from 'features/cases'
import { PageScaffold } from 'shared/ui'

export function CaseDetailPage() {
  const { caseId } = useParams({ strict: false })
  const { data: caseDetail, isLoading, isError } = useCaseDetail(caseId ?? '')

  if (!caseId) {
    return null
  }

  if (isLoading) {
    return (
      <div className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <div className="h-5 w-40 animate-pulse rounded bg-slate-200" />
        <div className="mt-3 h-16 animate-pulse rounded bg-slate-100" />
      </div>
    )
  }

  if (isError || !caseDetail) {
    return (
      <div className="rounded-[2rem] border border-red-100 bg-red-50 p-6">
        <p className="text-sm text-red-600">Failed to load case overview.</p>
      </div>
    )
  }

  return (
    <PageScaffold
      title="Case Overview"
      description="Operational metadata for the active case shell."
    >
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
            Location
          </p>
          <p className="mt-2 text-sm text-slate-700">
            {caseDetail.location.addressLabel ?? 'No address has been captured yet.'}
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
            Source
          </p>
          <p className="mt-2 text-sm capitalize text-slate-700">{caseDetail.source}</p>
        </section>
      </div>
    </PageScaffold>
  )
}
