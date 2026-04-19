import type { EffectiveWorkType } from '../types/workCatalog.types'

export interface WorkTypeAvailability {
  allowedCodes: ReadonlySet<string>
  recommendedCodes: ReadonlySet<string>
}

export function getWorkTypeAvailability(
  workTypes: readonly EffectiveWorkType[],
  caseStatus: string,
): WorkTypeAvailability {
  const allowed = new Set<string>()
  const recommended = new Set<string>()

  for (const workType of workTypes) {
    if (workType.phaseBinding.allowedCaseStates.includes(caseStatus)) {
      allowed.add(workType.code)
    }

    if (workType.phaseBinding.recommendedCaseStates.includes(caseStatus)) {
      recommended.add(workType.code)
    }
  }

  return {
    allowedCodes: allowed,
    recommendedCodes: recommended,
  }
}
