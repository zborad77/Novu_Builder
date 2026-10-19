import { apiClient } from 'shared/lib/apiClient'
import type { CaseDetail } from '../types/case.types'
import type { PhotoListResponse, PolygonPoint } from 'shared/types/photo.types'

export function fetchCaseDetail(caseId: string, signal?: AbortSignal): Promise<CaseDetail> {
  return apiClient.get<CaseDetail>(`/cases/${caseId}`, undefined, signal ? { signal } : {})
}

export function fetchCasePhotos(caseId: string, signal?: AbortSignal): Promise<PhotoListResponse> {
  return apiClient.get<PhotoListResponse>(`/cases/${caseId}/images`, undefined, signal ? { signal } : {})
}

export interface AnalysisSelectionBody {
  polygon?: PolygonPoint[]
  manualAreaSqm?: number | null
}

export interface AnalysisSelectionSaved {
  id: string
  status: string
}

export function saveAnalysisSelection(
  caseId: string,
  resultId: string,
  body: AnalysisSelectionBody,
  signal?: AbortSignal,
): Promise<AnalysisSelectionSaved> {
  return apiClient.patch<AnalysisSelectionSaved>(
    `/cases/${caseId}/analysis-results/${resultId}/selection`,
    body,
    signal ? { signal } : {},
  )
}

/**
 * Domain commit: marks the measurement as manually confirmed.
 * Sets finalAreaSource = 'manual' so the selection becomes a pricing
 * artefact rather than a visual annotation.  Must be called AFTER
 * saveAnalysisSelection has persisted the polygon + manualAreaSqm.
 */
export function confirmMeasurement(
  measurementId: string,
  signal?: AbortSignal,
): Promise<{ id: string }> {
  return apiClient.post<{ id: string }>(
    `/measurements/${measurementId}/confirm`,
    undefined,
    signal ? { signal } : {},
  )
}

export interface CaseTimelineEvent {
  seq?: number
  eventType: string
  label: string
  occurredAt: string | null
  payload: Record<string, unknown>
}

export function fetchCaseTimeline(caseId: string, signal?: AbortSignal): Promise<CaseTimelineEvent[]> {
  return apiClient.get<CaseTimelineEvent[]>(`/cases/${caseId}/timeline`, undefined, signal ? { signal } : {})
}
