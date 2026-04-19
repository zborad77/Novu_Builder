import { useParams } from '@tanstack/react-router'
import { useToast } from 'app/providers/ToastProvider'
import { useCaseWorkspace } from 'features/cases'
import {
  getTreePathLabel,
  useCaseWorkItems,
  useCaseWorkItemActions,
  useEffectiveWorkTypes,
  WorkTypeCommandPalette,
} from 'features/work-catalog'
import { PageScaffold } from 'shared/ui'
import { ApiError } from 'shared/types/api.types'

export function CaseWorkItemsPage() {
  const { caseId } = useParams({ strict: false })
  const { toast } = useToast()
  const { caseDetail } = useCaseWorkspace()
  const {
    data: workItemsResponse,
    isLoading: isWorkItemsLoading,
    isError: isWorkItemsError,
  } = useCaseWorkItems(caseId ?? '')
  const { data: effectiveWorkTypes } = useEffectiveWorkTypes()
  const { createWorkItem, isCreatingWorkItem } = useCaseWorkItemActions(caseId ?? '')

  if (!caseId) {
    return null
  }

  const workItems = [...(workItemsResponse?.items ?? [])].sort(
    (left, right) => left.itemSequence - right.itemSequence,
  )
  const workTypeMeta = new Map(
    (effectiveWorkTypes?.items ?? []).map((item) => [
      item.code,
      {
        displayName: item.effectiveDisplayName,
        categoryName: item.category.name,
        measurementKind: item.measurementKind,
      },
    ]),
  )

  async function handleCreateWorkItem(wtCode: string) {
    try {
      const created = await createWorkItem(wtCode)
      const label = workTypeMeta.get(created.workTypeCode)?.displayName ?? created.title
      toast.success(`Work item ${label} was added.`)
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : 'Failed to create the work item.'
      toast.error(message)
      throw error
    }
  }

  return (
    <PageScaffold
      title="Case Work Items"
      description="Picker stays case-phase aware, highlights recommended work types and lets operators create items in a fast command-palette flow."
    >
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-5 shadow-sm">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-xs font-semibold uppercase tracking-[0.26em] text-emerald-600">
                Add Work Item
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950">
                Search the catalog without leaving the case flow
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                The picker respects the current case phase, keeps unavailable work types visible
                for context and surfaces recommended options first.
              </p>
            </div>

            <div className="w-full max-w-xl">
              <WorkTypeCommandPalette
                caseStatus={caseDetail.status}
                onSelect={handleCreateWorkItem}
                disabled={isCreatingWorkItem}
              />
            </div>
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              Existing Items
            </p>
            <p className="mt-1 text-sm text-slate-600">
              {workItems.length} item{workItems.length === 1 ? '' : 's'} in this case
            </p>
          </div>

          {isWorkItemsLoading ? (
            <div className="grid gap-3 md:grid-cols-2">
              {Array.from({ length: 4 }, (_, index) => (
                <div
                  key={index}
                  className="h-40 animate-pulse rounded-[1.5rem] border border-slate-200 bg-white"
                />
              ))}
            </div>
          ) : null}

          {isWorkItemsError ? (
            <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
              Failed to load work items for this case.
            </div>
          ) : null}

          {!isWorkItemsLoading && !isWorkItemsError && workItems.length === 0 ? (
            <div className="rounded-[2rem] border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center">
              <p className="text-sm font-medium text-slate-700">No work items yet.</p>
              <p className="mt-2 text-sm text-slate-500">
                Open the picker above and create the first scoped work item for this case.
              </p>
            </div>
          ) : null}

          {!isWorkItemsLoading && !isWorkItemsError && workItems.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {workItems.map((item) => {
                const meta = workTypeMeta.get(item.workTypeCode)
                const pathLabel = getTreePathLabel(item.workTypeCode)

                return (
                  <article
                    key={item.id}
                    className="rounded-[1.5rem] border border-slate-200 bg-white p-4 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                          Item {item.itemSequence}
                        </p>
                        <h3 className="mt-2 text-base font-semibold text-slate-950">
                          {meta?.displayName ?? item.title}
                        </h3>
                        <p className="mt-1 text-sm text-slate-500">
                          {meta?.categoryName ?? item.categoryCode}
                        </p>
                      </div>

                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                        {item.status}
                      </span>
                    </div>

                    {pathLabel ? (
                      <p className="mt-3 text-sm leading-6 text-slate-600">{pathLabel}</p>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                        {meta?.measurementKind ?? 'manual'}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                        {item.defaultUnit}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
                        {item.sourceType}
                      </span>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-600">
                      <div className="rounded-2xl bg-slate-50 px-3 py-2">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
                          Values
                        </p>
                        <p className="mt-1 font-medium text-slate-800">{item.values.length}</p>
                      </div>
                      <div className="rounded-2xl bg-slate-50 px-3 py-2">
                        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
                          Confirmation
                        </p>
                        <p className="mt-1 font-medium text-slate-800">{item.confirmationStatus}</p>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          ) : null}
        </section>
      </div>
    </PageScaffold>
  )
}
