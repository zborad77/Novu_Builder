import { useCreateCaseWorkItem } from '../api/workCatalogQueries'
import type { ProjectWorkItem } from '../types/workCatalog.types'

interface UseCaseWorkItemActionsResult {
  createWorkItem: (wtCode: string) => Promise<ProjectWorkItem>
  isCreatingWorkItem: boolean
}

export function useCaseWorkItemActions(caseId: string): UseCaseWorkItemActionsResult {
  const createWorkItemMutation = useCreateCaseWorkItem(caseId)

  async function createWorkItem(wtCode: string) {
    return createWorkItemMutation.mutateAsync({ workTypeCode: wtCode })
  }

  return {
    createWorkItem,
    isCreatingWorkItem: createWorkItemMutation.isPending,
  }
}
