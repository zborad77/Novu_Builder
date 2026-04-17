export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  role: string;
  isActive: boolean;
  organizationId: string;
  isSuperAdmin: boolean;
}

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  user: AuthUser;
}

export interface ProjectSummary {
  id: string;
  title: string;
  status: string;
  propertyType: string | null;
  repairScope: string | null;
  addressLabel: string | null;
  photoCount: number;
  estimatedAreaSqm: number | null;
  latestQuoteTotal: number | null;
  updatedAt: string | null;
  createdByName: string | null;
}

export interface ProjectListResponse {
  items: ProjectSummary[];
  total: number;
}

export interface ProjectCreate {
  title: string;
  description?: string;
  source: 'mobile';
  locationLat?: number;
  locationLng?: number;
  addressLabel?: string;
  propertyType?: string;
  repairScope?: string;
}

export interface ProjectCreateResponse {
  id: string;
  status: string;
}

export interface PhotoUploadResponse {
  id: string;
  filename: string;
  url: string;
}

export const PROPERTY_TYPES = [
  { label: 'Rodinný dům', value: 'house' },
  { label: 'Bytový dům', value: 'apartment_building' },
  { label: 'Komerční objekt', value: 'commercial' },
  { label: 'Průmyslový objekt', value: 'industrial' },
  { label: 'Jiné', value: 'other' },
] as const;

export const REPAIR_SCOPES = [
  { label: 'Střecha', value: 'roof' },
  { label: 'Fasáda', value: 'facade' },
  { label: 'Okna a dveře', value: 'windows_doors' },
  { label: 'Interiér', value: 'interior' },
  { label: 'Základy', value: 'foundations' },
  { label: 'Jiné', value: 'other' },
] as const;

// ── Markers ────────────────────────────────────────────────────────────────

export type MarkerType =
  | 'note'
  | 'defect'
  | 'ai_detection'
  | 'measurement';

/** Controls mutability. 'user' = editable, 'ai' = immutable / pipeline-written. */
export type MarkerSource = 'user' | 'ai';

export interface Marker {
  id: string;
  caseId: string;
  imageId: string | null;
  markerType: MarkerType;
  markerSource: MarkerSource;
  x: number;       // normalised 0–1
  y: number;       // normalised 0–1
  width: number | null;
  height: number | null;
  label: string;
  severity: string | null;
  createdBy: string | null;
  createdAt: string;
}

export interface MarkerCreate {
  caseId: string;
  imageId?: string;
  markerType: MarkerType;
  x: number;
  y: number;
  width?: number;
  height?: number;
  label: string;
  severity?: string;
}

export interface MarkerListResponse {
  items: Marker[];
}

// ── Project status ──────────────────────────────────────────────────────────

export const PROJECT_STATUS_LABELS: Record<string, string> = {
  new: 'Nová',
  in_progress: 'Zpracovává se',
  draft: 'Návrh',
  ready: 'Připravena',
  sent: 'Odesláno',
  archived: 'Archivováno',
};
