/**
 * Data container for WorkTree.
 *
 * Responsibilities:
 *   1. Fetch all effective work types.
 *   2. Compute allowedCodes / recommendedCodes from phase binding + case status.
 *   3. Pass static WORK_TREE + computed sets to the pure WorkTree component.
 *
 * What this container must not do:
 *   - Filter or modify WORK_TREE.
 *   - Pass a pre-filtered subset of WORK_TREE to WorkTree.
 */
import { useMemo } from 'react'
import { useEffectiveWorkTypes } from '../api/workCatalogQueries'
import { WorkTree } from '../components/WorkTree'
import { WORK_TREE } from '../config/workTreeConfig'
import type { WorkTypeSelectHandler } from '../types/workCatalog.types'
import { getWorkTypeAvailability } from '../utils/workTypeAvailability'

interface CaseWorkTreeProps {
  caseStatus: string
  onSelect?: WorkTypeSelectHandler | undefined
}

export function CaseWorkTree({ caseStatus, onSelect }: CaseWorkTreeProps) {
  const { data, isLoading, isError } = useEffectiveWorkTypes()

  const { allowedCodes, recommendedCodes } = useMemo(
    () => getWorkTypeAvailability(data?.items ?? [], caseStatus),
    [data, caseStatus],
  )

  if (isLoading) {
    return (
      <div className="space-y-3">
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
    <WorkTree
      tree={WORK_TREE}
      allowedCodes={allowedCodes}
      recommendedCodes={recommendedCodes}
      onSelect={onSelect}
    />
  )
}
