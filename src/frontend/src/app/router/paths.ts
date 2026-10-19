/**
 * Typed URL helpers — single source of truth for all route paths.
 * Import this instead of writing strings in <Link to="..." /> or navigate().
 *
 * This is NOT a parallel router system — it is only a path constant/factory file.
 */

export const paths = {
  home: '/',

  // Auth
  login: '/login',
  forgotPassword: '/forgot-password',
  resetPassword: '/reset-password',

  // Cases
  cases: '/cases',
  caseDetail: (caseId: string) => `/cases/${caseId}` as const,
  casePhotos: (caseId: string) => `/cases/${caseId}/photos` as const,
  casePhotoViewer: (caseId: string, imageId: string) =>
    `/cases/${caseId}/photos/${imageId}` as const,
  caseWorkItems: (caseId: string) => `/cases/${caseId}/work-items` as const,
  caseEstimates: (caseId: string) => `/cases/${caseId}/estimates` as const,
  caseExports: (caseId: string) => `/cases/${caseId}/exports` as const,
  caseTimeline: (caseId: string) => `/cases/${caseId}/timeline` as const,

  // Catalog
  catalogWorkTypes: '/catalog/work-types',
  catalogMaterials: '/catalog/materials',
  catalogPricebooks: '/catalog/pricebooks',

  // Settings
  settingsProfile: '/settings/profile',
  settingsSuppliers: '/settings/suppliers',

  // Tools
  archiveViewer: '/archive-viewer',

  // Admin
  adminCompanies: '/admin/companies',
  adminCompanyDetail: (companyId: string) => `/admin/companies/${companyId}` as const,
  adminUsers: '/admin/users',
  adminJobs: '/admin/jobs',
  adminAudit: '/admin/audit',
} as const
