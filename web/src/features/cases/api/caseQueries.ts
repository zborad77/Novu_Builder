import { useQuery } from '@tanstack/react-query'
import { fetchCaseDetail } from './caseApi'

export const CASE_KEYS = {
  all: ['cases'] as const,
  list: () => [...CASE_KEYS.all, 'list'] as const,
  detail: (id: string) => ['project', id] as const,
} as const

export function useCaseDetail(caseId: string) {
  return useQuery({
    queryKey: CASE_KEYS.detail(caseId),
    queryFn: ({ signal }) => fetchCaseDetail(caseId, signal),
    enabled: caseId.length > 0,
    staleTime: 30_000,
  })
}
