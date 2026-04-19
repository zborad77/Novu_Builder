import { apiClient } from 'shared/lib/apiClient'
import type {
  EffectiveWorkTypeListResponse,
  ProjectWorkItem,
  ProjectWorkItemCreateInput,
  ProjectWorkItemListResponse,
  ProjectWorkTypeEffectiveConfiguration,
} from '../types/workCatalog.types'

export function fetchEffectiveWorkTypes(signal?: AbortSignal): Promise<EffectiveWorkTypeListResponse> {
  return apiClient.get<EffectiveWorkTypeListResponse>(
    '/work-catalog/work-types',
    undefined,
    signal ? { signal } : {},
  )
}

export function fetchCaseWorkTypeEffectiveConfiguration(
  caseId: string,
  workTypeCode: string,
  signal?: AbortSignal,
): Promise<ProjectWorkTypeEffectiveConfiguration> {
  return apiClient.get<ProjectWorkTypeEffectiveConfiguration>(
    `/cases/${caseId}/work-types/${workTypeCode}/effective-configuration`,
    undefined,
    signal ? { signal } : {},
  )
}

export function fetchCaseWorkItems(
  caseId: string,
  signal?: AbortSignal,
): Promise<ProjectWorkItemListResponse> {
  return apiClient.get<ProjectWorkItemListResponse>(
    `/cases/${caseId}/work-items`,
    undefined,
    signal ? { signal } : {},
  )
}

export function createCaseWorkItem(
  caseId: string,
  payload: ProjectWorkItemCreateInput,
): Promise<ProjectWorkItem> {
  return apiClient.post<ProjectWorkItem>(`/cases/${caseId}/work-items`, payload)
}
