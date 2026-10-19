import { apiClient } from 'shared/lib/apiClient'
import { CASE_ACTIONS, type CaseActionName } from 'shared/api/generated/caseWorkflow'
import type { CaseDetail } from '../types/case.types'

// API klient: mapování akce workflow na endpoint backendu. Kdy je akce dostupná,
// její popisek a zda vyžaduje důvod určuje backend (`availableTransitions`).
// `satisfies Record<CaseActionName, …>` zajistí, že nová akce v kontraktu
// (src/contracts/workflow) bez endpointu zde neprojde typovou kontrolou.
const CASE_ACTION_ENDPOINTS = {
  submit: 'submit',
  start_analysis: 'start-analysis',
  approve_proposal: 'approve-proposal',
  send_quote: 'send',
  complete: 'archive',
  return_to_draft: 'return-to-draft',
  cancel: 'cancel',
} as const satisfies Record<CaseActionName, string>

export type CaseAction = CaseActionName

export function isCaseAction(action: string): action is CaseAction {
  return (CASE_ACTIONS as readonly string[]).includes(action)
}

export function executeCaseAction(
  caseId: string,
  action: CaseAction,
  payload: { reason?: string } = {},
): Promise<CaseDetail> {
  return apiClient.post<CaseDetail>(`/cases/${caseId}/${CASE_ACTION_ENDPOINTS[action]}`, payload)
}
