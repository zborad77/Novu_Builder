import { useCaseWorkTypeCatalog } from '../api/workCatalogQueries'

interface CaseWorkTypeCatalogProps {
  caseId: string
}

export function CaseWorkTypeCatalog({ caseId }: CaseWorkTypeCatalogProps) {
  const { items, isLoading, isError } = useCaseWorkTypeCatalog(caseId)

  if (isLoading) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 6 }, (_, index) => (
          <div
            key={index}
            className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="h-4 w-32 animate-pulse rounded bg-slate-200" />
            <div className="mt-3 h-3 w-full animate-pulse rounded bg-slate-100" />
            <div className="mt-2 h-3 w-24 animate-pulse rounded bg-slate-100" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
        Failed to load case-ready work types.
      </div>
    )
  }

  const allowedItems = items
    .filter((item) => item.effectiveWorkType.phaseBinding.allowedInCurrentCaseState === true)
    .sort((left, right) => {
      const leftRecommended =
        left.effectiveWorkType.phaseBinding.recommendedInCurrentCaseState === true ? 1 : 0
      const rightRecommended =
        right.effectiveWorkType.phaseBinding.recommendedInCurrentCaseState === true ? 1 : 0

      if (leftRecommended !== rightRecommended) {
        return rightRecommended - leftRecommended
      }

      return left.effectiveWorkType.effectiveDisplayName.localeCompare(
        right.effectiveWorkType.effectiveDisplayName,
      )
    })

  if (allowedItems.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
        No work types are currently available in this case phase.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        <span>Case-ready work types</span>
        <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-emerald-700">
          Recommended first
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {allowedItems.map((item) => {
          const { effectiveWorkType } = item
          const recommended =
            effectiveWorkType.phaseBinding.recommendedInCurrentCaseState === true

          return (
            <article
              key={effectiveWorkType.code}
              className={[
                'rounded-[1.5rem] border bg-white p-4 shadow-sm transition',
                recommended
                  ? 'border-emerald-300 ring-2 ring-emerald-100'
                  : 'border-slate-200',
              ].join(' ')}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-950">
                    {effectiveWorkType.effectiveDisplayName}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                    {effectiveWorkType.category.name}
                  </p>
                </div>
                {recommended ? (
                  <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                    Recommended
                  </span>
                ) : null}
              </div>

              {effectiveWorkType.description ? (
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  {effectiveWorkType.description}
                </p>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                  {effectiveWorkType.measurementKind}
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                  {effectiveWorkType.defaultUnit}
                </span>
                {effectiveWorkType.phaseBinding.visionDetectable ? (
                  <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700">
                    Vision-ready
                  </span>
                ) : null}
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}
