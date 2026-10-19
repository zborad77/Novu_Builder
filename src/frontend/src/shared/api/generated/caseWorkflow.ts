// VYGENEROVÁNO z src/contracts – NEUPRAVOVAT RUČNĚ.
// Přegenerování: npm run gen:contracts (kontrakty generuje backend: python -m scripts.export_contracts).

export const CASE_STATUSES = ["draft","intake","analyzing","proposal_ready","quote_ready","sent","archived","cancelled"] as const

export type CaseStatus = (typeof CASE_STATUSES)[number]

export const TERMINAL_CASE_STATUSES: readonly CaseStatus[] = ["archived","cancelled"]

export const LOCKED_CASE_STATUSES: readonly CaseStatus[] = ["analyzing","proposal_ready","quote_ready","sent"]

export const CASE_ACTIONS = ["submit","cancel","start_analysis","return_to_draft","approve_proposal","send_quote","complete"] as const

export type CaseActionName = (typeof CASE_ACTIONS)[number]
