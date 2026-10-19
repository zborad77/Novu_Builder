import { CASE_STATUSES, TERMINAL_CASE_STATUSES } from 'shared/api/generated/caseWorkflow'
import type { CaseStatus } from '../types/case.types'

// Prezentační popisky stavů; pořadí fází a terminální stavy pocházejí z kontraktu
// workflow (src/contracts/workflow), který generuje backend.
const PHASE_LABELS: Record<CaseStatus, { label: string; shortLabel: string }> = {
  draft: { label: 'Draft', shortLabel: 'Draft' },
  intake: { label: 'Intake', shortLabel: 'Intake' },
  analyzing: { label: 'Analyzing', shortLabel: 'Analysis' },
  proposal_ready: { label: 'Proposal ready', shortLabel: 'Proposal' },
  quote_ready: { label: 'Quote ready', shortLabel: 'Quote' },
  sent: { label: 'Sent', shortLabel: 'Sent' },
  archived: { label: 'Archived', shortLabel: 'Done' },
  cancelled: { label: 'Cancelled', shortLabel: 'Cancelled' },
}

const CASE_PHASES = CASE_STATUSES.map((code) => ({ code, ...PHASE_LABELS[code] }))

function isTerminal(status: CaseStatus): status is 'archived' | 'cancelled' {
  return TERMINAL_CASE_STATUSES.includes(status)
}

const TERMINAL_TONE: Record<Extract<CaseStatus, 'archived' | 'cancelled'>, string> = {
  archived: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  cancelled: 'border-red-200 bg-red-50 text-red-700',
}

interface CasePhaseIndicatorProps {
  status: CaseStatus
}

export function CasePhaseIndicator({ status }: CasePhaseIndicatorProps) {
  if (isTerminal(status)) {
    return (
      <div
        className={`rounded-2xl border px-4 py-3 text-sm font-medium ${TERMINAL_TONE[status]}`}
      >
        {CASE_PHASES.find((phase) => phase.code === status)?.label ?? status}
      </div>
    )
  }

  const activeIndex = CASE_PHASES.findIndex((phase) => phase.code === status)
  const linearPhases = CASE_PHASES.filter((phase) => !isTerminal(phase.code))

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/90 px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
        Phase
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {linearPhases.map((phase, index) => {
          const isComplete = index < activeIndex
          const isActive = phase.code === status

          return (
            <div
              key={phase.code}
              className={[
                'inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-semibold',
                isActive
                  ? 'border-emerald-300 bg-emerald-100 text-emerald-800'
                  : isComplete
                    ? 'border-slate-200 bg-white text-slate-600'
                    : 'border-slate-200 bg-white text-slate-400',
              ].join(' ')}
            >
              {phase.shortLabel}
            </div>
          )
        })}
      </div>
    </div>
  )
}
