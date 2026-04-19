import type { CaseStatus } from '../types/case.types'

const STATUS_STYLES: Record<CaseStatus, string> = {
  draft:          'bg-slate-100   text-slate-600',
  intake:         'bg-blue-100    text-blue-700',
  analyzing:      'bg-amber-100   text-amber-700',
  proposal_ready: 'bg-purple-100  text-purple-700',
  quote_ready:    'bg-indigo-100  text-indigo-700',
  sent:           'bg-emerald-100 text-emerald-700',
  archived:       'bg-slate-200   text-slate-500',
  cancelled:      'bg-red-100     text-red-600',
}

const STATUS_LABEL: Record<CaseStatus, string> = {
  draft:          'Draft',
  intake:         'Intake',
  analyzing:      'Analyzing',
  proposal_ready: 'Proposal ready',
  quote_ready:    'Quote ready',
  sent:           'Sent',
  archived:       'Archived',
  cancelled:      'Cancelled',
}

interface CaseStatusBadgeProps {
  status: CaseStatus
}

export function CaseStatusBadge({ status }: CaseStatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-600'}`}
    >
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}
