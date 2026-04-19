import type { CaseStatus } from '../types/case.types'

const CASE_PHASES: Array<{
  code: CaseStatus
  label: string
  shortLabel: string
}> = [
  { code: 'draft', label: 'Draft', shortLabel: 'Draft' },
  { code: 'intake', label: 'Intake', shortLabel: 'Intake' },
  { code: 'analyzing', label: 'Analyzing', shortLabel: 'Analysis' },
  { code: 'proposal_ready', label: 'Proposal ready', shortLabel: 'Proposal' },
  { code: 'quote_ready', label: 'Quote ready', shortLabel: 'Quote' },
  { code: 'sent', label: 'Sent', shortLabel: 'Sent' },
  { code: 'archived', label: 'Archived', shortLabel: 'Done' },
  { code: 'cancelled', label: 'Cancelled', shortLabel: 'Cancelled' },
]

const TERMINAL_TONE: Record<Extract<CaseStatus, 'archived' | 'cancelled'>, string> = {
  archived: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  cancelled: 'border-red-200 bg-red-50 text-red-700',
}

interface CasePhaseIndicatorProps {
  status: CaseStatus
}

export function CasePhaseIndicator({ status }: CasePhaseIndicatorProps) {
  if (status === 'archived' || status === 'cancelled') {
    return (
      <div
        className={`rounded-2xl border px-4 py-3 text-sm font-medium ${TERMINAL_TONE[status]}`}
      >
        {CASE_PHASES.find((phase) => phase.code === status)?.label ?? status}
      </div>
    )
  }

  const activeIndex = CASE_PHASES.findIndex((phase) => phase.code === status)
  const linearPhases = CASE_PHASES.slice(0, 6)

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
