import { useMutation, useQueryClient } from '@tanstack/react-query'
import { executeCaseAction, type CaseAction } from '../api/caseActionsApi'
import { CASE_KEYS } from '../api/caseQueries'

interface ExecuteCaseActionInput {
  action: CaseAction
  reason?: string
}

export function useCaseActions(caseId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ action, reason }: ExecuteCaseActionInput) =>
      executeCaseAction(caseId, action, reason !== undefined ? { reason } : {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: CASE_KEYS.detail(caseId) })
    },
  })
}
