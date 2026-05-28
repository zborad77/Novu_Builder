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

import type { AnalysisResult } from 'shared/types/photo.types'

export interface ProposalPricingSnapshot {
  hourlyRate: number
  dailyRate: number
  laborHoursPerSqm: number
  marginEconomyPct: number
  marginStandardPct: number
  marginPremiumPct: number
  vatPct: number
  currency: string
}

export interface ProposalInputVersions {
  analysisProfileCode: string | null
  analysisProfileVersion: number | null
  catalogPricingProfileCode: string | null
  catalogPricingProfileVersion: number | null
  pricingProfileId: string | null
  pricingProfileSnapshot: ProposalPricingSnapshot | null
}

export interface FinalProposal {
  id: string
  status: string
  draftVersion: number
  currency: string
  totalPrice: number | null
  analysisResultId: string | null
  inputVersions: ProposalInputVersions | null
  createdAt: string | null
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
  latestAnalysis: AnalysisResult | null
  finalProposal: FinalProposal | null
  createdAt: string | null
  updatedAt: string | null
}
