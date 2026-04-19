/**
 * Combines search + tree view for case-context work type selection.
 *
 * query empty -> full WorkTree (all leaves, allowed/recommended overlay)
 * query >= 2  -> WorkTreeSearch results (scored, sorted, with overlay)
 *
 * The tree is never filtered; only the active view changes.
 */
import { useMemo, useState } from 'react'
import { useEffectiveWorkTypes } from '../api/workCatalogQueries'
import { WorkTree } from '../components/WorkTree'
import { WorkTreeSearch } from '../components/WorkTreeSearch'
import { WORK_TREE } from '../config/workTreeConfig'
import { WORK_TREE_SEARCH_INDEX } from '../config/workTreeSearchIndex'
import { useWorkTreeSearch } from '../hooks/useWorkTreeSearch'
import type { WorkTypeSelectHandler } from '../types/workCatalog.types'
import { getWorkTypeAvailability } from '../utils/workTypeAvailability'

interface CaseWorkTypePickerProps {
  caseStatus: string
  autoFocusSearch?: boolean | undefined
  onSelect?: WorkTypeSelectHandler | undefined
}

export function CaseWorkTypePicker({
  caseStatus,
  autoFocusSearch = false,
  onSelect,
}: CaseWorkTypePickerProps) {
  const { data, isLoading, isError } = useEffectiveWorkTypes()
  const [query, setQuery] = useState('')

  const { allowedCodes, recommendedCodes } = useMemo(
    () => getWorkTypeAvailability(data?.items ?? [], caseStatus),
    [data, caseStatus],
  )

  const { results, isActive } = useWorkTreeSearch({
    query,
    index: WORK_TREE_SEARCH_INDEX,
    allowedCodes,
    recommendedCodes,
  })

  function handleSelectWorkType(wtCode: string) {
    return onSelect?.(wtCode)
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="h-10 animate-pulse rounded-xl border border-slate-200 bg-white" />
        {Array.from({ length: 4 }, (_, index) => (
          <div
            key={index}
            className="h-16 animate-pulse rounded-2xl border border-slate-200 bg-white"
          />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
        Nepodarilo se nacist katalog typu praci.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <WorkTreeSearch
        query={query}
        onQueryChange={setQuery}
        results={results}
        isActive={isActive}
        autoFocus={autoFocusSearch}
        onSelect={handleSelectWorkType}
      />

      {!isActive && (
        <WorkTree
          tree={WORK_TREE}
          allowedCodes={allowedCodes}
          recommendedCodes={recommendedCodes}
          onSelect={handleSelectWorkType}
        />
      )}
    </div>
  )
}
