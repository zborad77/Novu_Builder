import { apiClient, type ApiStreamOptions } from 'shared/lib/apiClient'

// SSE stream událostí zakázky přes /bff/api; session nese HttpOnly cookie (žádný token v JS).
export function openCaseEventStream(caseId: string, opts: ApiStreamOptions): Promise<Response> {
  return apiClient.stream(`/cases/${caseId}/activity/stream`, opts)
}
