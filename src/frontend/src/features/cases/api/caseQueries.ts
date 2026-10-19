import { useQuery } from '@tanstack/react-query'
import { fetchCaseDetail, fetchCasePhotos, fetchCaseTimeline } from './caseApi'

export const CASE_KEYS = {
  all: ['cases'] as const,
  list: () => [...CASE_KEYS.all, 'list'] as const,
  detail: (id: string) => ['project', id] as const,
  photos: (id: string) => ['project', id, 'photos'] as const,
  timeline: (id: string) => ['project', id, 'timeline'] as const,
} as const

export function useCaseDetail(caseId: string) {
  return useQuery({
    queryKey: CASE_KEYS.detail(caseId),
    queryFn: ({ signal }) => fetchCaseDetail(caseId, signal),
    enabled: caseId.length > 0,
    staleTime: 30_000,
  })
}

export function usePhotos(caseId: string) {
  return useQuery({
    queryKey: CASE_KEYS.photos(caseId),
    queryFn: ({ signal }) => fetchCasePhotos(caseId, signal),
    enabled: caseId.length > 0,
    staleTime: 60_000,
  })
}

export function useCaseTimeline(caseId: string) {
  return useQuery({
    queryKey: CASE_KEYS.timeline(caseId),
    queryFn: ({ signal }) => fetchCaseTimeline(caseId, signal),
    enabled: caseId.length > 0,
    staleTime: 30_000,
  })
}
