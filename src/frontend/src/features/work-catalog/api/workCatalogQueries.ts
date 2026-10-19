import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCaseWorkItem,
  fetchCaseWorkItems,
  fetchCaseWorkTypeEffectiveConfiguration,
  fetchEffectiveWorkTypes,
} from './workCatalogApi'
import type {
  ProjectWorkItemCreateInput,
  ProjectWorkTypeEffectiveConfiguration,
} from '../types/workCatalog.types'

export const WORK_CATALOG_KEYS = {
  all: ['work-catalog'] as const,
  effectiveList: () => [...WORK_CATALOG_KEYS.all, 'effective-list'] as const,
  caseItems: (caseId: string) => ['project', caseId, 'work-items'] as const,
  caseEffectiveConfig: (caseId: string, workTypeCode: string) =>
    ['project', caseId, 'work-types', workTypeCode] as const,
} as const

export function useEffectiveWorkTypes() {
  return useQuery({
    queryKey: WORK_CATALOG_KEYS.effectiveList(),
    queryFn: ({ signal }) => fetchEffectiveWorkTypes(signal),
    staleTime: 60_000,
  })
}

export function useCaseWorkTypeCatalog(caseId: string) {
  const effectiveWorkTypesQuery = useEffectiveWorkTypes()
  const workTypes = effectiveWorkTypesQuery.data?.items ?? []

  const configurationQueries = useQueries({
    queries: workTypes.map((workType) => ({
      queryKey: WORK_CATALOG_KEYS.caseEffectiveConfig(caseId, workType.code),
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        fetchCaseWorkTypeEffectiveConfiguration(caseId, workType.code, signal),
      enabled: caseId.length > 0,
      staleTime: 30_000,
    })),
  })

  const items = configurationQueries
    .map((query) => query.data)
    .filter((item): item is ProjectWorkTypeEffectiveConfiguration => item !== undefined)

  return {
    items,
    isLoading:
      effectiveWorkTypesQuery.isLoading ||
      (workTypes.length > 0 && configurationQueries.some((query) => query.isLoading)),
    isError:
      effectiveWorkTypesQuery.isError || configurationQueries.some((query) => query.isError),
  }
}

export function useCaseWorkItems(caseId: string) {
  return useQuery({
    queryKey: WORK_CATALOG_KEYS.caseItems(caseId),
    queryFn: ({ signal }) => fetchCaseWorkItems(caseId, signal),
    enabled: caseId.length > 0,
    staleTime: 15_000,
  })
}

export function useCreateCaseWorkItem(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ProjectWorkItemCreateInput) => createCaseWorkItem(caseId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: WORK_CATALOG_KEYS.caseItems(caseId) })
    },
  })
}
