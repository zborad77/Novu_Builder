import { apiClient, type ApiStreamOptions } from 'shared/lib/apiClient'

// SSE stream událostí zakázky; apiClient.stream vlastní base URL a Authorization hlavičku.
export function openCaseEventStream(caseId: string, opts: ApiStreamOptions): Promise<Response> {
  return apiClient.stream(`/cases/${caseId}/activity/stream`, opts)
}
