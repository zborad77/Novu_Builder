import { useState } from 'react'
import { ReasonDialog } from 'shared/ui'
import {
  ACTION_CONFIG,
  getCaseActionConfig,
  isCaseAction,
  type CaseAction,
} from '../api/caseActionsApi'
import { useCaseActions } from '../hooks/useCaseActions'
import type { AvailableTransition, CaseStatus } from '../types/case.types'

const ACTION_STYLE: Record<string, string> = {
  submit: 'bg-emerald-600 text-white hover:bg-emerald-700',
  start_analysis: 'bg-emerald-600 text-white hover:bg-emerald-700',
  approve_proposal: 'bg-emerald-600 text-white hover:bg-emerald-700',
  send_quote: 'bg-emerald-600 text-white hover:bg-emerald-700',
  complete: 'bg-emerald-600 text-white hover:bg-emerald-700',
  return_to_draft: 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
  cancel: 'border border-red-200 bg-white text-red-600 hover:bg-red-50',
}

const BASE_BUTTON_CLASS =
  'inline-flex items-center rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50'

const STATUS_LABEL: Record<CaseStatus, string> = {
  draft: 'Draft',
  intake: 'Intake',
  analyzing: 'Analyzing',
  proposal_ready: 'Proposal ready',
  quote_ready: 'Quote ready',
  sent: 'Sent',
  archived: 'Archived',
  cancelled: 'Cancelled',
}

interface PendingTransition {
  action: CaseAction
  label: string
  reason: string
}

type ConfiguredTransition = AvailableTransition & {
  action: CaseAction
}

interface CaseWorkflowActionsProps {
  caseId: string
  status: CaseStatus
  availableTransitions: AvailableTransition[]
}

export function CaseWorkflowActions({
  caseId,
  status,
  availableTransitions,
}: CaseWorkflowActionsProps) {
  const { mutate, isPending } = useCaseActions(caseId)
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null)
  const statusLabel = STATUS_LABEL[status] ?? status
  const visibleTransitions: ConfiguredTransition[] = availableTransitions.flatMap((transition) =>
    isCaseAction(transition.action)
      ? [{
          ...transition,
          action: transition.action,
        }]
      : [],
  )

  if (visibleTransitions.length === 0) {
    return null
  }

  function openTransition(transition: ConfiguredTransition) {
    const config = getCaseActionConfig(transition.action)
    if (!config) {
      return
    }

    if (config.requiresReason) {
      setPendingTransition({
        action: transition.action,
        label: config.label,
        reason: '',
      })
      return
    }

    mutate({ action: transition.action })
  }

  function confirmPendingTransition() {
    if (!pendingTransition) {
      return
    }

    const payload =
      pendingTransition.reason.trim().length > 0
        ? { action: pendingTransition.action, reason: pendingTransition.reason.trim() }
        : { action: pendingTransition.action }

    mutate(payload, {
      onSettled: () => setPendingTransition(null),
    })
  }

  return (
    <section aria-label={`Workflow actions for ${statusLabel} case`} className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {visibleTransitions.map((transition) => {
          const config = ACTION_CONFIG[transition.action]

          return (
            <button
              key={transition.action}
              type="button"
              className={`${BASE_BUTTON_CLASS} ${ACTION_STYLE[transition.action] ?? ACTION_STYLE['return_to_draft']}`}
              disabled={isPending}
              onClick={() => openTransition(transition)}
            >
              {config.label}
            </button>
          )
        })}
      </div>

      <ReasonDialog
        open={pendingTransition !== null}
        title={pendingTransition?.label ?? 'Workflow note'}
        description="This workflow transition requires a reason."
        value={pendingTransition?.reason ?? ''}
        isPending={isPending}
        onChange={(reason) => {
          if (!pendingTransition) {
            return
          }

          setPendingTransition({
            ...pendingTransition,
            reason,
          })
        }}
        onConfirm={confirmPendingTransition}
        onClose={() => setPendingTransition(null)}
      />
    </section>
  )
}
