/**
 * Photo and analysis result types — mirrors python-backend schemas.
 *
 * ProjectPhotoRead  → schema/photo.py :: ProjectPhotoRead
 * AnalysisResult    → schema/analysis.py :: AnalysisResultRead
 *
 * maskPolygon coordinates are in the coordinate space of the AI-input image
 * variant (the resized image the vision API processed).  Render using the
 * aiInput variant dimensions as the viewBox, or normalize by dividing by
 * aiInput.width / aiInput.height.
 */

export interface PhotoVariant {
  storageKey: string | null
  fileSize: number | null
  width: number | null
  height: number | null
  url: string | null
}

export interface PhotoVariants {
  original: PhotoVariant
  preview: PhotoVariant
  aiInput: PhotoVariant
}

export interface PhotoRead {
  id: string
  projectId: string
  originalFilename: string
  storageKey: string
  mimeType: string
  fileSize: number
  width: number | null
  height: number | null
  takenAt: string | null
  exifLat: number | null
  exifLng: number | null
  processingStatus: string
  isPrimary: boolean
  isAnalysisReference: boolean
  sortOrder: number
  url: string
  variants: PhotoVariants
}

export interface PhotoListMeta {
  minimumRecommendedCount: number
  hasMinimumCount: boolean
  primaryPhotoId: string | null
  analysisReferencePhotoId: string | null
  derivativeStrategy: Record<string, string>
}

export interface PhotoListResponse {
  items: PhotoRead[]
  meta: PhotoListMeta
}

// ---------------------------------------------------------------------------
// Analysis result
// ---------------------------------------------------------------------------

export interface PolygonPoint {
  x: number
  y: number
}

/**
 * A user-drawn repair polygon anchored to a specific analysis version.
 *
 * Invariant: if latestAnalysis.id changes, this selection MUST be discarded.
 * This holds across: overlay refresh, reconnect, proposal recompute, replay.
 *
 * Qt parity: the C++ viewer must implement the same anchor check before
 * committing a selectedRepairPolygon to the backend.
 */
export interface OverlaySelection {
  /** latestAnalysis.id at the moment the user started drawing. */
  analysisId: string
  /** User-drawn polygon in aiInput pixel coordinates. */
  polygon: PolygonPoint[]
  /**
   * AI-estimated area captured at confirm time.
   * When set, the save flow sends manualAreaSqm to the backend so the
   * selection becomes a pricing artefact (finalAreaSource = 'manual'),
   * not just a visual annotation.
   */
  confirmedAreaSqm?: number | null
}

/**
 * Mirrors AnalysisResultRead from schema/analysis.py.
 *
 * maskPolygon — AI-detected damage area in aiInput image pixel coordinates.
 * selectedRepairPolygon — user override drawn on the photo.
 * referencePhotoId — the photo the overlay belongs to (guards against stale overlays).
 */
export interface AnalysisResult {
  id: string
  projectId: string
  analysisJobId: string | null
  workTypeCode: string | null
  analysisProfileCode: string | null
  analysisProfileVersion: number | null
  referencePhotoId: string | null
  objectType: string | null
  surfaceCondition: string | null
  recommendedScope: string | null
  estimatedQuantity: number | null
  estimatedUnit: string | null
  estimatedAreaSqm: number | null
  areaConfidence: number | null
  selectedRepairPolygon: PolygonPoint[] | null
  manualAreaSqm: number | null
  finalAreaSource: string
  maskPolygon: PolygonPoint[] | null
  materials: Record<string, unknown>[] | null
  workflowSteps: Record<string, unknown>[] | null
  estimatedDurationDays: number | null
  laborHoursTotal: number | null
  modelName: string | null
  modelVersion: string | null
  createdAt: string | null
}
