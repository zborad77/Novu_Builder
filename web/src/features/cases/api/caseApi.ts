import { apiClient } from 'shared/lib/apiClient'
import type { CaseDetail } from '../types/case.types'

export function fetchCaseDetail(caseId: string, signal?: AbortSignal): Promise<CaseDetail> {
  return apiClient.get<CaseDetail>(`/cases/${caseId}`, undefined, signal ? { signal } : {})
}
