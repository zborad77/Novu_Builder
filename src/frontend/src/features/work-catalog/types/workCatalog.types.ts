export interface WorkTypePhaseBinding {
  allowedCaseStates: string[]
  recommendedCaseStates: string[]
  visionDetectable: boolean
  currentCaseStatus: string | null
  allowedInCurrentCaseState: boolean | null
  recommendedInCurrentCaseState: boolean | null
}

export type WorkTypeSelectHandler = (wtCode: string) => void | Promise<void>

export interface WorkTypeCategory {
  code: string
  slug: string
  name: string
  description: string | null
  sortOrder: number
  catalogVersion: number
}

export interface EffectiveWorkType {
  code: string
  slug: string
  name: string
  description: string | null
  state: string
  isEnabled: boolean
  effectiveDisplayName: string
  category: WorkTypeCategory
  defaultUnit: string
  measurementKind: string
  workTypeVersion: number
  settingVersion: number | null
  phaseBinding: WorkTypePhaseBinding
  analysisProfile: { code: string } | null
  catalogPricingProfile: { code: string } | null
  tenantPricingProfileId: string | null
}

export interface EffectiveWorkTypeListResponse {
  items: EffectiveWorkType[]
  total: number
}

export interface ProjectWorkTypeEffectiveConfiguration {
  projectId: string
  caseStatus: string
  workTypeCode: string
  effectiveWorkType: EffectiveWorkType
}

export interface ProjectWorkItemValue {
  parameterDefinitionId: string
  parameterScope: string
  parameterCode: string
  parameterSlug: string
  parameterLabel: string
  parameterSection: string | null
  dataType: string
  unit: string | null
  visionExtractable: boolean | null
  manualOverrideAllowed: boolean | null
  textValue: string | null
  numberValue: number | null
  booleanValue: boolean | null
  optionValue: string | null
  sourceType: string
  sourceConfidence: number | null
  sourceDetectionId: string | null
  confirmationStatus: string
  confirmedByUserId: string | null
  confirmedAt: string | null
  operatorNote: string | null
  updatedAt: string | null
}

export interface ProjectWorkItem {
  id: string
  projectId: string
  workTypeCode: string
  categoryCode: string
  title: string
  status: string
  sourceType: string
  confirmationStatus: string
  itemSequence: number
  measuredQuantity: number | null
  measuredUnit: string | null
  defaultUnit: string
  workTypeVersion: number
  settingVersion: number | null
  analysisProfileCode: string | null
  analysisProfileVersion: number | null
  catalogPricingProfileCode: string | null
  catalogPricingProfileVersion: number | null
  tenantPricingProfileId: string | null
  notes: string | null
  confirmedByUserId: string | null
  confirmedAt: string | null
  values: ProjectWorkItemValue[]
  detections: unknown[]
  createdAt: string | null
  updatedAt: string | null
}

export interface ProjectWorkItemListResponse {
  items: ProjectWorkItem[]
  total: number
}

export interface ProjectWorkItemCreateInput {
  workTypeCode: string
  title?: string
  sourceType?: string
  status?: string
  measuredQuantity?: number | null
  measuredUnit?: string | null
  notes?: string | null
  values?: unknown[]
}
