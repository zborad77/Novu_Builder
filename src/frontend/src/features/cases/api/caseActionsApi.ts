import { apiClient } from 'shared/lib/apiClient'
import type { CaseDetail } from '../types/case.types'

type CaseActionConfig = {
  label: string
  requiresReason: boolean
  path: string
}

export const ACTION_CONFIG = {
  submit: {
    label: 'Submit for intake',
    requiresReason: false,
    path: 'submit',
  },
  start_analysis: {
    label: 'Start analysis',
    requiresReason: false,
    path: 'start-analysis',
  },
  approve_proposal: {
    label: 'Approve proposal',
    requiresReason: false,
    path: 'approve-proposal',
  },
  send_quote: {
    label: 'Send quote to client',
    requiresReason: false,
    path: 'send',
  },
  complete: {
    label: 'Mark as completed',
    requiresReason: false,
    path: 'archive',
  },
  return_to_draft: {
    label: 'Return to draft',
    requiresReason: true,
    path: 'return-to-draft',
  },
  cancel: {
    label: 'Cancel case',
    requiresReason: true,
    path: 'cancel',
  },
} as const satisfies Record<string, CaseActionConfig>

export type CaseAction = keyof typeof ACTION_CONFIG

export function isCaseAction(action: string): action is CaseAction {
  return action in ACTION_CONFIG
}

export function getCaseActionConfig(action: string): (typeof ACTION_CONFIG)[CaseAction] | null {
  if (!isCaseAction(action)) {
    return null
  }

  return ACTION_CONFIG[action]
}

export function executeCaseAction(
  caseId: string,
  action: CaseAction,
  payload: { reason?: string } = {},
): Promise<CaseDetail> {
  return apiClient.post<CaseDetail>(`/cases/${caseId}/${ACTION_CONFIG[action].path}`, payload)
}
