export type CaseStatus =
  | 'draft'
  | 'intake'
  | 'analyzing'
  | 'proposal_ready'
  | 'quote_ready'
  | 'sent'
  | 'archived'
  | 'cancelled'

export interface AvailableTransition {
  action: string
  label: string
  requires_reason: boolean
}

export interface CaseLocation {
  lat: number | null
  lng: number | null
  addressLabel: string | null
}

export interface CaseSummary {
  id: string
  title: string
  status: CaseStatus
  propertyType: string | null
  repairScope: string | null
  addressLabel: string | null
  photoCount: number
  updatedAt: string | null
  createdByName: string | null
}

export interface CaseDetail {
  id: string
  title: string
  description: string | null
  status: CaseStatus
  source: string
  propertyType: string | null
  repairScope: string | null
  location: CaseLocation
  availableTransitions: AvailableTransition[]
  photos: unknown[]
  latestAnalysis: Record<string, unknown> | null
  createdAt: string | null
  updatedAt: string | null
}
