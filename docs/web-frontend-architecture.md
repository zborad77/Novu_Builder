# Web Frontend Architecture

src/
│
├── main.tsx
│
├── app/
│ ├── guards/
│ │ ├── AuthGuard.tsx redirect → /login pokud není autentizovaný actor
│ │ │ po resolve auth state (ne jen přítomnost tokenu —
│ │ │ token může existovat ale session může být neplatná)
│ │ ├── AdminGuard.tsx redirect pokud realActor není superadmin
│ │ │ DŮLEŽITÉ: rozhoduje nad realActor, ne effectiveActor —
│ │ │ superadmin při impersonaci nesmí ztratit admin přístup
│ │ └── OrgGuard.tsx redirect pokud user nemá organizationId
│ │ POZOR: superadmin smí být bez organizationId —
│ │ guard musí mít výjimku pro superadmin role;
│ │ používá actorContext.canAccessOrgScopedRoute()
│ ├── layouts/
│ │ ├── AppShell.tsx hlavní shell (sidebar, nav, toast area)
│ │ │ renderuje ImpersonateBanner globálně
│ │ ├── AuthLayout.tsx obal pro login / forgot / reset stránky
│ │ ├── CaseLayout.tsx outlet + CaseTabNav + CaseMetaPanel sidebar
│ │ └── AdminLayout.tsx admin sekce shell
│ ├── providers/
│ │ ├── AuthProvider.tsx autentizace — realActor z JWT, refresh on mount
│ │ │ vystavuje useRealActor() — skutečný přihlášený user,
│ │ │ nikdy impersonovaný; bezpečný pro audit/billing/security
│ │ ├── ImpersonationProvider.tsx musí být uvnitř AuthProvider
│ │ │ vlastní: isImpersonating, effectiveActor
│ │ │ čte z AuthProvider: realActor (není vlastněný stav)
│ │ │ viz sekce Impersonation a Actor API
│ │ ├── QueryProvider.tsx TanStack Query client
│ │ └── ToastProvider.tsx
│ └── router/
│ ├── index.tsx router definice (TanStack Router) — source of truth
│ ├── paths.ts typed URL helpery; není paralelní router systém
│ ├── RouteErrorBoundary.tsx sdílený error component pro TanStack Router routes
│ │ krytí: auth refresh edge cases, case detail, viewer,
│ │ admin detail panely — každá route group dostane svůj
│ └── RoutePendingBoundary.tsx sdílený pending/loading component pro routes

│
├── pages/ tenké entry pointy — jen import + compose
│ ├── LoginPage.tsx
│ ├── ForgotPasswordPage.tsx
│ ├── ResetPasswordPage.tsx
│ ├── CaseListPage.tsx
│ ├── CaseDetailPage.tsx používá CaseLayout z app/layouts/
│ ├── CasePhotosPage.tsx
│ ├── PhotoViewerPage.tsx route param = source of truth pro aktuální image
│ │ fetchuje markery přes features/markers public API,
│ │ předává je jako props do PhotoViewer
│ ├── CaseWorkItemsPage.tsx
│ ├── CaseEstimatesPage.tsx
│ ├── CaseExportsPage.tsx
│ ├── CaseTimelinePage.tsx
│ ├── CatalogWorkTypesPage.tsx
│ ├── CatalogMaterialsPage.tsx
│ ├── CatalogPricebooksPage.tsx
│ ├── SettingsProfilePage.tsx
│ ├── SettingsSuppliersPage.tsx
│ ├── AdminCompaniesPage.tsx
│ ├── AdminCompanyDetailPage.tsx
│ ├── AdminUsersPage.tsx
│ ├── AdminJobsPage.tsx
│ ├── AdminAuditPage.tsx
│ └── NotFoundPage.tsx
│
├── features/
│ │
│ ├── auth/
│ │ ├── api/
│ │ │ ├── authApi.ts apiClient wrapper — login, logout, refresh, me, sessions
│ │ │ ├── authKeys.ts TanStack Query key factory
│ │ │ ├── useLogin.ts
│ │ │ ├── useLogout.ts
│ │ │ ├── useAuthMe.ts GET /auth/me — interní; vně používat useRealActor/
│ │ │ │ useEffectiveActor z features/impersonation
│ │ │ ├── useSessions.ts GET + DELETE /auth/sessions
│ │ │ ├── useChangePassword.ts
│ │ │ ├── useForgotPassword.ts
│ │ │ └── useResetPassword.ts
│ │ ├── components/
│ │ │ ├── LoginForm.tsx
│ │ │ ├── ForgotPasswordForm.tsx
│ │ │ ├── ResetPasswordForm.tsx
│ │ │ └── SessionList.tsx aktivní sessions + revoke tlačítko
│ │ ├── types/
│ │ │ └── auth.types.ts
│ │ └── index.ts PUBLIC API — vně importovat jen odtud
│ │
│ ├── cases/
│ │ ├── api/
│ │ │ ├── casesApi.ts apiClient wrapper
│ │ │ ├── caseKeys.ts TanStack Query key factory
│ │ │ │ all / lists / list(filters) / detail(id) / timeline(id)
│ │ │ ├── useCaseList.ts GET /cases
│ │ │ ├── useCase.ts GET /cases/:id
│ │ │ ├── useCreateCase.ts POST /cases
│ │ │ ├── useUpdateCase.ts PATCH /cases/:id
│ │ │ ├── useDuplicateCase.ts POST /cases/:id/duplicate
│ │ │ ├── useArchiveCase.ts POST /cases/:id/archive
│ │ │ ├── useSendCase.ts POST /cases/:id/send
│ │ │ ├── useFinalProposal.ts POST /cases/:id/final-proposal
│ │ │ ├── useProposalDraft.ts PATCH /cases/:id/proposal-draft
│ │ │ └── useCaseTimeline.ts GET /cases/:id/timeline
│ │ ├── components/
│ │ │ ├── CaseCard.tsx
│ │ │ ├── CaseStatusBadge.tsx
│ │ │ ├── CaseActionMenu.tsx duplicate / archive / send / export
│ │ │ ├── CaseMetaPanel.tsx sidebar s metadaty case
│ │ │ ├── CaseCreateModal.tsx
│ │ │ ├── CaseTabNav.tsx photos / work-items / estimates / exports / timeline
│ │ │ └── TimelineTab.tsx
│ │ ├── analysis/
│ │ │ ├── api/
│ │ │ │ ├── analysisJobsApi.ts apiClient wrapper
│ │ │ │ ├── analysisKeys.ts TanStack Query key factory
│ │ │ │ ├── useAnalysisJobs.ts GET /cases/:id/analysis-jobs
│ │ │ │ ├── useTriggerAnalysis.ts POST /cases/:id/analysis-jobs
│ │ │ │ ├── useCancelAnalysis.ts POST /analysis-jobs/:id/cancel
│ │ │ │ ├── useRetryAnalysis.ts POST /analysis-jobs/:id/retry
│ │ │ │ └── useAnalysisResultSelection.ts PATCH selection [optimistic candidate]
│ │ │ ├── components/
│ │ │ │ ├── AnalysisTriggerButton.tsx
│ │ │ │ ├── AnalysisJobStatusBadge.tsx pending/running/done/failed
│ │ │ │ └── AnalysisJobList.tsx
│ │ │ └── hooks/
│ │ │ └── useAnalysisPoller.ts interval refetch dokud status != terminal
│ │ ├── exports/
│ │ │ ├── api/
│ │ │ │ ├── exportsApi.ts apiClient wrapper
│ │ │ │ ├── exportKeys.ts TanStack Query key factory
│ │ │ │ ├── useCreateExport.ts POST /cases/:id/exports/\*
│ │ │ │ └── useExport.ts GET /exports/:id (stav + download URL)
│ │ │ ├── components/
│ │ │ │ ├── ExportsTab.tsx
│ │ │ │ └── ExportButton.tsx trigger + inline progress
│ │ │ ├── hooks/
│ │ │ │ └── useExportPoller.ts polling dokud status != ready/failed
│ │ │ └── types/
│ │ │ └── export.types.ts
│ │ ├── hooks/
│ │ │ └── useCaseStatusLabel.ts enum → display string + color
│ │ ├── types/
│ │ │ └── case.types.ts
│ │ └── index.ts PUBLIC API — vně importovat jen odtud
│ │ orchestruje analysis + exports jako subfeatures;
│ │ jejich internals nejsou součástí public API
│ │
│ ├── photos/
│ │ ├── api/
│ │ │ ├── photosApi.ts apiClient wrapper
│ │ │ ├── photoKeys.ts TanStack Query key factory
│ │ │ │ all / byCase(caseId) / detail(imgId) / previewUrl(imgId)
│ │ │ ├── usePhotos.ts GET /cases/:id/images
│ │ │ ├── useUploadPhoto.ts POST /cases/:id/images (multipart)
│ │ │ ├── useDeletePhoto.ts DELETE /cases/:id/images/:imgId
│ │ │ ├── useSetPrimaryPhoto.ts PATCH …/primary [optimistic candidate]
│ │ │ ├── useSetAnalysisReference.ts PATCH …/analysis-reference
│ │ │ └── useMovePhoto.ts PATCH …/move [optimistic candidate — drag UX]
│ │ ├── components/
│ │ │ ├── PhotosTab.tsx grid + upload zone + toolbar
│ │ │ ├── PhotoGrid.tsx
│ │ │ ├── PhotoCard.tsx thumbnail + badge + hover menu
│ │ │ ├── PhotoUploadZone.tsx drag & drop + file picker
│ │ │ └── PhotoActionMenu.tsx set primary / set ref / delete
│ │ ├── viewer/
│ │ │ ├── PhotoViewer.tsx fullscreen shell (keyboard nav, zoom)
│ │ │ │ aktuální image ID čte z route param,
│ │ │ │ ne ze store — deep link a back/fwd musí fungovat;
│ │ │ │ markery dostává jako props z PhotoViewerPage,
│ │ │ │ neimportuje features/markers přímo
│ │ │ ├── ViewerImageStage.tsx <img> + <MarkerOverlay> composite
│ │ │ │ MarkerOverlay dostává markery přes props,
│ │ │ │ ne přímým importem z features/markers
│ │ │ └── ViewerToolbar.tsx zoom in/out, fit, next/prev
│ │ ├── hooks/
│ │ │ ├── usePhotoSort.ts lokální reorder stav před PATCH
│ │ │ └── usePhotoPreviewUrl.ts GET /images/:id/preview → redirect URL
│ │ ├── types/
│ │ │ └── photo.types.ts
│ │ └── index.ts PUBLIC API — photos je záměrně nezávislá feature
│ │
│ ├── markers/
│ │ ├── api/
│ │ │ ├── markersApi.ts apiClient wrapper
│ │ │ ├── markerKeys.ts TanStack Query key factory
│ │ │ │ all / byCase(caseId) / byImage(imageId) / detail(id)
│ │ │ ├── useMarkers.ts GET /markers?case_id= nebo ?image_id=
│ │ │ ├── useCreateMarker.ts POST /markers
│ │ │ └── useDeleteMarker.ts DELETE /markers/:id
│ │ ├── components/
│ │ │ ├── MarkerOverlay.tsx SVG vrstva, 0–1 normalizované souřadnice
│ │ │ ├── MarkerPin.tsx vizuální pin (barva = type + severity)
│ │ │ ├── MarkerPanel.tsx sidebar: detail existujícího / form nového
│ │ │ └── MarkerTypeIcon.tsx defect / note / ai_detection / measurement
│ │ ├── hooks/
│ │ │ └── useMarkerDraft.ts dočasné coords z kliknutí před submitem
│ │ ├── types/
│ │ │ └── marker.types.ts
│ │ └── utils/
│ │ ├── markerCoords.ts px ↔ 0–1 konverze
│ │ └── markerColors.ts type/severity → tailwind/hex token
│ │ PUBLIC API přes index.ts;
│ │ viewer konzumuje markery přes props, ne přímým importem
│ │
│ ├── work-items/
│ │ ├── api/
│ │ │ ├── workItemsApi.ts apiClient wrapper
│ │ │ ├── workItemKeys.ts TanStack Query key factory
│ │ │ ├── useWorkItems.ts GET /cases/:id/work-items
│ │ │ ├── useWorkItemDetail.ts GET …/:itemId
│ │ │ ├── useAddWorkItem.ts POST /cases/:id/work-items
│ │ │ ├── useUpdateWorkItemValues.ts PUT + PATCH + merge /values [optimistic candidate]
│ │ │ ├── useConfirmWorkItem.ts POST …/confirm
│ │ │ └── useAddVisionDetection.ts POST …/detections
│ │ ├── components/
│ │ │ ├── WorkItemsTab.tsx
│ │ │ ├── WorkItemCard.tsx
│ │ │ ├── WorkItemValueForm.tsx
│ │ │ ├── WorkItemSearchModal.tsx browse katalog → add
│ │ │ └── VisionDetectionBadge.tsx
│ │ ├── types/
│ │ │ └── workItem.types.ts
│ │ └── index.ts PUBLIC API — importuje detections; viewer internals ne
│ │
│ ├── estimates/
│ │ ├── api/
│ │ │ ├── estimatesApi.ts apiClient wrapper
│ │ │ ├── estimateKeys.ts TanStack Query key factory
│ │ │ ├── useEstimates.ts GET /cases/:id/estimates
│ │ │ └── useCreateEstimate.ts POST
│ │ ├── components/
│ │ │ ├── EstimatesTab.tsx
│ │ │ ├── EstimateVariantCard.tsx
│ │ │ └── EstimateSummary.tsx
│ │ ├── types/
│ │ │ └── estimate.types.ts
│ │ └── index.ts PUBLIC API
│ │
│ ├── impersonation/ cross-cutting concern — vlastní feature, ne admin detail
│ │ ├── api/
│ │ │ ├── impersonationApi.ts apiClient wrapper — POST /admin/impersonate/:id + DELETE
│ │ │ └── useImpersonate.ts spustí impersonaci → ImpersonationProvider.set
│ │ ├── components/
│ │ │ └── ImpersonateBanner.tsx viditelná lišta při impersonaci
│ │ │ renderována v AppShell, ne jen v admin sekci
│ │ ├── hooks/
│ │ │ ├── useEffectiveActor.ts → effectiveActor pro běžný UI svět
│ │ │ ├── useRealActor.ts → skutečný přihlášený superadmin
│ │ │ └── useImpersonationContext.ts
│ │ │ → { isImpersonating, realActor, effectiveActor }
│ │ │ čte z ImpersonationProvider
│ │ └── types/
│ │ └── impersonation.types.ts
│ │
│ ├── catalog/
│ │ ├── work-types/
│ │ │ ├── api/
│ │ │ │ ├── workCatalogApi.ts apiClient wrapper
│ │ │ │ ├── workCatalogKeys.ts TanStack Query key factory
│ │ │ │ ├── useWorkTypes.ts GET effective work-types
│ │ │ │ ├── useWorkTypeDetail.ts GET catalog work-type detail
│ │ │ │ ├── useCatalogCategories.ts GET categories
│ │ │ │ ├── useCatalogWorkTypes.ts GET catalog list (globální)
│ │ │ │ └── useUpdateWorkTypeSettings.ts PUT settings (tenant override)
│ │ │ └── components/
│ │ │ ├── WorkTypesTable.tsx
│ │ │ ├── WorkTypeSettingsForm.tsx
│ │ │ └── CategoryFilter.tsx
│ │ ├── materials/
│ │ │ ├── api/
│ │ │ │ ├── materialCatalogApi.ts apiClient wrapper
│ │ │ │ ├── materialKeys.ts TanStack Query key factory
│ │ │ │ ├── useMaterials.ts GET /material-catalog
│ │ │ │ ├── useUpdateMaterial.ts PATCH
│ │ │ │ └── useSupplierPrices.ts GET /:id/supplier-prices
│ │ │ └── components/
│ │ │ ├── MaterialsTable.tsx
│ │ │ └── MaterialEditModal.tsx
│ │ ├── pricebooks/
│ │ │ ├── api/
│ │ │ │ ├── pricebooksApi.ts apiClient wrapper
│ │ │ │ ├── pricebookKeys.ts TanStack Query key factory
│ │ │ │ ├── usePricebooks.ts GET /pricebooks
│ │ │ │ ├── useCreatePricebook.ts POST
│ │ │ │ └── usePricebookItems.ts GET /:id/items
│ │ │ └── components/
│ │ │ ├── PricebooksTable.tsx
│ │ │ └── PricebookItemList.tsx
│ │ └── types/
│ │ └── catalog.types.ts
│ │
│ ├── settings/
│ │ ├── profile/
│ │ │ └── components/ čistě compose vrstva — žádná vlastní API doména
│ │ │ ├── ChangePasswordForm.tsx importuje useChangePassword z features/auth
│ │ │ └── SessionsManager.tsx importuje useSessions z features/auth
│ │ └── suppliers/
│ │ ├── api/
│ │ │ ├── suppliersApi.ts apiClient wrapper
│ │ │ ├── supplierKeys.ts TanStack Query key factory
│ │ │ ├── useSuppliers.ts GET /suppliers
│ │ │ └── useUpdateSupplier.ts PATCH /:id
│ │ └── components/
│ │ ├── SuppliersTable.tsx
│ │ └── SupplierEditForm.tsx
│ │
│ └── admin/
│ ├── companies/
│ │ ├── api/
│ │ │ ├── adminCompaniesApi.ts apiClient wrapper
│ │ │ ├── adminCompanyKeys.ts TanStack Query key factory
│ │ │ ├── useAdminCompanies.ts GET /admin/companies
│ │ │ ├── useAdminCompany.ts GET /admin/companies/:id
│ │ │ ├── useCreateCompany.ts POST
│ │ │ └── useUpdateCompany.ts PATCH
│ │ └── components/
│ │ ├── CompaniesTable.tsx
│ │ ├── CompanyForm.tsx
│ │ └── CompanyDetailPanel.tsx
│ ├── users/
│ │ ├── api/
│ │ │ ├── adminUsersApi.ts apiClient wrapper
│ │ │ ├── adminUserKeys.ts TanStack Query key factory
│ │ │ ├── useAdminUsers.ts
│ │ │ ├── useAdminUser.ts
│ │ │ ├── useCreateUser.ts
│ │ │ ├── useUpdateUser.ts
│ │ │ └── useAdminResetPassword.ts POST /:id/reset-password
│ │ │ useImpersonate → features/impersonation/
│ │ └── components/
│ │ ├── UsersTable.tsx
│ │ └── UserForm.tsx
│ │ ImpersonateBanner → features/impersonation/
│ ├── jobs/
│ │ ├── api/
│ │ │ ├── adminJobsApi.ts apiClient wrapper
│ │ │ ├── adminJobKeys.ts TanStack Query key factory
│ │ │ ├── useAdminJobs.ts GET /admin/jobs
│ │ │ ├── useAdminJob.ts GET /admin/jobs/:id
│ │ │ ├── useRetryJob.ts POST …/retry
│ │ │ └── useReprocessJob.ts POST …/reprocess
│ │ └── components/
│ │ ├── JobsTable.tsx
│ │ ├── JobDetailPanel.tsx
│ │ └── JobStatusBadge.tsx
│ └── audit/
│ ├── api/
│ │ ├── adminAuditApi.ts apiClient wrapper
│ │ ├── adminAuditKeys.ts TanStack Query key factory
│ │ └── useAuditLog.ts GET /admin/audit
│ └── components/
│ └── AuditLogTable.tsx
│
├── shared/
│ ├── ui/
│ │ ├── Button.tsx
│ │ ├── Modal.tsx
│ │ ├── ConfirmDialog.tsx
│ │ ├── Toast.tsx
│ │ ├── Skeleton.tsx
│ │ ├── Badge.tsx
│ │ ├── Table.tsx
│ │ ├── Tabs.tsx
│ │ ├── Spinner.tsx
│ │ ├── EmptyState.tsx
│ │ ├── forms/
│ │ │ ├── FormField.tsx label + error wrapper pro libovolný input
│ │ │ ├── TextInput.tsx
│ │ │ ├── SelectField.tsx
│ │ │ ├── NumberInput.tsx
│ │ │ └── TextArea.tsx
│ │ └── index.ts barrel export — zde barrel ano
│ ├── lib/
│ │ ├── apiClient.ts axios instance — jediný HTTP transport;
│ │ │ JWT interceptor, 401→refresh, error normalize,
│ │ │ abort/cancel signal, auth headers
│ │ │ raw fetch napřímo je zakázán
│ │ ├── queryClient.ts TanStack Query config (staleTime, retry)
│ │ ├── actorContext.ts isSuperAdmin / hasOrganizationContext /
│ │ │ isEffectiveTenantActor /
│ │ │ canAccessOrgScopedRoute /
│ │ │ isGlobalAdminContext
│ │ │ vstupy: Actor objekt z useRealActor /
│ │ │ useEffectiveActor — nikdy není vnitřně hookový
│ │ ├── permissions.ts canManageCase / canCreateMarker / …
│ │ │ volá actorContext helpery interně
│ │ └── errorMap.ts backend error kód → UI hláška
│ │ (auth / validation / rate-limit / 403 / 404)
│ ├── hooks/
│ │ ├── usePolling.ts generický interval poller (analysis + exports)
│ │ └── useDebounce.ts
│ ├── types/
│ │ ├── api.types.ts ApiError, PaginatedResponse<T>
│ │ └── index.ts
│ └── utils/
│ ├── cn.ts classnames helper
│ ├── formatDate.ts
│ └── formatCurrency.ts
│
└── store/
├── uiStore.ts čistě shell state:
│ sidebar open, mobile menu, transient UI toggles
│ POZOR: active tab NENÍ v store pokud jsou taby
│ route-driven — source of truth = URL
└── viewerStore.ts pouze UI state vieweru:
zoom, panX, panY,
activeMarkerId, isCreateMarkerMode,
draftMarkerCoords, showAiMarkers,
showUserMarkers
POZOR: currentImageId NENÍ ve store —
source of truth = route param (deep link,
back/fwd navigace, keyboard next/prev)

---

## Pravidla

### Transport layer — jediný HTTP klient

Všechny `*Api.ts` soubory jsou **wrappery nad `shared/lib/apiClient`**, nikdy volají `fetch` ani `axios` přímo.

`apiClient` řeší centrálně:

- JWT header injection
- 401 → token refresh → **jednorázový** retry (ne loop)
- error normalizaci (viz `errorMap.ts`)
- abort/cancel signal (předáván přes TanStack Query `signal`)
- auth hlavičky

Chování při selhání refresh tokenu:

- refresh request selže → `apiClient` provede logout (clear token storage)
- `AuthProvider` resetuje auth stav včetně `realActor`
- `ImpersonationProvider` resetuje pouze impersonation stav — `effectiveActor = null`
- inflight requesty dostanou chybu, nezkoušejí se znovu
- router zachytí unauthenticated stav přes `AuthGuard` → redirect na `/login`
- **retry loop prevence**: request označený jako `_isRefreshRetry` se nepokouší o další refresh

```ts
// ✓ správně
import { apiClient } from 'shared/lib/apiClient'
export const casesApi = { list: () => apiClient.get('/cases') }

// ❌ zakázáno
export const casesApi = { list: () => fetch('/cases', { headers: { Authorization: … } }) }
```

### Feature public API

Vně feature importovat **pouze** z `features/<name>/index.ts`.

```ts
import { CaseCard, useCase } from "features/cases"; // ✓
import { CaseCard } from "features/cases/components/CaseCard"; // ❌
import { useCase } from "features/cases/api/useCase"; // ❌
```

### Actor API — kdo jsem?

Tři explicitní hooks; `useAuthMe` se nepoužívá vně auth feature:

| Hook                        | Vrací                                            | Kdy použít                                      |
| --------------------------- | ------------------------------------------------ | ----------------------------------------------- |
| `useEffectiveActor()`       | effectiveActor (nebo realActor)                  | běžný UI svět — zobrazení jména, oprávnění v UI |
| `useRealActor()`            | skutečný přihlášený superadmin                   | audit, billing, security-sensitive logika       |
| `useImpersonationContext()` | `{ isImpersonating, realActor, effectiveActor }` | impersonation UI, banner, guard                 |

`permissions.ts` a `actorContext.ts` dostávají Actor objekt jako argument — nejsou hookové.

### Cross-feature závislosti

Povolený směr:

- `photos` — nezávislá; neimportuje z jiných features; `PhotoViewerPage` (pages/) smí importovat `features/markers` public API a marker data předat dolů jako props — coupling je na úrovni page, ne uvnitř feature
- `markers` — doména; viewer konzumuje marker data přes props předané z `PhotoViewerPage`, nikoli přímým importem uvnitř `photos/viewer/`
- `work-items` — konzumuje detections data; neimportuje viewer internals
- `cases` — orchestruje analysis + exports jako subfeatures; nepohltí jejich implementaci
- `impersonation` — cross-cutting; internals features/impersonation jsou off-limits pro jiné features;
  compose/aplikační vrstva (AppShell, layouts, guards) smí importovat public API features/impersonation;
  business features (cases, photos…) nesmí mít na impersonation přímou závislost
- `settings/profile` — čistě compose; žádná vlastní API doména, importuje z `features/auth`

Cyklické závislosti jsou vždy chyba.

### Route-level error + loading boundaries

Každá route group dostane svůj `errorComponent` a `pendingComponent` v TanStack Router:

| Route group         | Důvod                                          |
| ------------------- | ---------------------------------------------- |
| case detail + tabs  | nested fetches, analysis polling               |
| viewer              | heavy stav, auth refresh race                  |
| admin detail panely | impersonace může změnit oprávnění za běhu      |
| auth routes         | edge case: expirovaný token při reset-password |

Loading/error UX se **neřeší** roztříštěně po komponentách.

### Query key naming contract

Striktní naming — dodržovat konzistentně v celém kódu:

| Vzor                       | Použití                             |
| -------------------------- | ----------------------------------- |
| `xyzKeys.all`              | kořen — pro hromadnou invalidaci    |
| `xyzKeys.lists()`          | všechny list queries                |
| `xyzKeys.list(filters)`    | konkrétní list s filtry             |
| `xyzKeys.detail(id)`       | konkrétní entita                    |
| `xyzKeys.byCase(caseId)`   | resource scoped pod case            |
| `xyzKeys.byImage(imageId)` | resource scoped pod image (markery) |

Factory musí mít konzistentní hierarchii a každý vzor musí mít jasný sémantický důvod.
`detail(id)` a `byCase(caseId)` mohou v téže factory koexistovat pokud reprezentují různé
access patterny téže domény (markers: detail jednoho markeru vs. sada pod case/image).
Chyba je nekonzistentní nebo duplicitní naming bez jasného rozlišení.

### Query key invalidace — matice

| Mutace                       | Invaliduje                                               | Optimistic?           |
| ---------------------------- | -------------------------------------------------------- | --------------------- |
| `useUpdateCase`              | `caseKeys.detail(id)`, `caseKeys.lists()`                | —                     |
| `useArchiveCase`             | `caseKeys.detail(id)`, `caseKeys.lists()`                | —                     |
| `useTriggerAnalysis`         | `analysisKeys.byCase(id)`                                | —                     |
| `useAnalysisResultSelection` | `analysisKeys.byCase(id)`, `workItemKeys.byCase(id)`     | ✓ candidate           |
| `useUploadPhoto`             | `photoKeys.byCase(caseId)`, `caseKeys.detail(caseId)`    | —                     |
| `useDeletePhoto`             | `photoKeys.byCase(caseId)`, `caseKeys.detail(caseId)`    | —                     |
| `useSetPrimaryPhoto`         | `photoKeys.byCase(caseId)`, `caseKeys.detail(caseId)`    | ✓ candidate           |
| `useMovePhoto`               | `photoKeys.byCase(caseId)`                               | ✓ candidate — drag UX |
| `useCreateMarker`            | `markerKeys.byImage(imgId)`, `markerKeys.byCase(caseId)` | —                     |
| `useDeleteMarker`            | `markerKeys.byImage(imgId)`, `markerKeys.byCase(caseId)` | —                     |
| `useAddWorkItem`             | `workItemKeys.byCase(id)`                                | —                     |
| `useUpdateWorkItemValues`    | `workItemKeys.detail(itemId)`, `workItemKeys.byCase(id)` | ✓ candidate           |
| `useConfirmWorkItem`         | `workItemKeys.detail(itemId)`, `caseKeys.detail(caseId)` | —                     |
| `useCreateEstimate`          | `estimateKeys.byCase(id)`                                | —                     |
| `useImpersonate`             | `authKeys.me` + tenant-scoped actor-sensitive queries    | —                     |

Optimistic candidates používají `setQueryData` + rollback v `onError`.
Ostatní jen invalidují — čekají na server response.

### Impersonation — sémantika

`ImpersonationProvider` (uvnitř `AuthProvider`) drží:

- `realActor` — autentizovaný superadmin (z JWT, nemění se)
- `effectiveActor` — impersonovaný user (null = normální session)
- `isImpersonating` — derived bool

Pravidla:

- `useEffectiveActor()` = co vidí UI — pro většinu komponent
- `useRealActor()` = skutečný přihlášený admin — pro audit, billing, security checks
- `permissions.ts` a `actorContext.ts` dostávají Actor jako argument, nejsou hookové
- `ImpersonateBanner` renderován globálně v `AppShell`, ne jen v admin sekci
- ukončení i zahájení impersonace → DELETE/POST + reset provideru + `authKeys.me` invalidace
  - invalidace tenant-scoped queries (cases, photos, work-items…) — předchozí actor mohl
    mít jiný tenant kontext; starý snapshot nesmí přežít změnu effectiveActor
- auditní log na backendu musí vždy logovat `realActor`, ne `effectiveActor`

### CaseLayout — ownership

`CaseLayout` vlastní:

- base case detail query (`useCase`) — jeden fetch, ne duplicitní v každém tabu
- shell strukturu (outlet, sidebar)
- `CaseMetaPanel` a `CaseTabNav`
- společné loading a error state pro celou case detail sekci

Jednotlivé tab pages (`CasePhotosPage`, `CaseWorkItemsPage`, …) vlastní **pouze** tab-specific data.

Proč: bez tohoto pravidla každý tab začne fetchovat case detail zvlášť → duplicate fetching
a nekonzistentní loading/error UX v nejkritičtější části appky.

### Mutation side-effects — ownership

Mutace nesmí scatterovat navigaci, toasty a query invalidaci nahodile přes vrstvy.

Striktní ownership:

| Vrstva          | Zodpovídá za                                        |
| --------------- | --------------------------------------------------- |
| hook (`useFoo`) | server request, query invalidace, optimistic update |
| page / compose  | navigace po akci, toast / UX messaging              |

Pravidla:

- hook **nesmí** volat `navigate()` ani zobrazovat toast přímo
- page **nesmí** ručně volat `queryClient.invalidateQueries` — to je věc hooku
- výjimky musí být explicitně zdokumentované; jinak se side effects začnou rozlézat

### Barrel exporty

- `shared/ui/index.ts` — ano
- `features/*/index.ts` — ano (public API boundary)
- Interní barrel soubory uvnitř feature — opatrně, jen kde přidávají hodnotu

---

## Implementační rizika

Tato sekce popisuje místa, kde je návrh správný, ale implementační disciplína může časem erodovat. Nejde o chyby návrhu — jsou to body, kde je potřeba systematické code review.

### 1. Governed architektura vyžaduje code review kulturu

Pravidla v tomto dokumentu jsou silná a konzistentní. To je výhoda — ale znamená, že porušení jsou tichá a nenápadná, ne explicitní chyby kompilátoru.

Typická místa porušení pod tlakem:

- import mimo `features/*/index.ts` ("jen tentokrát, je to urgentní")
- hook volá `useToast()` přímo ("je to jeden řádek")
- page volá `queryClient.invalidateQueries` ("hook to nestihne invalidovat správně")
- feature sahá do internals jiné feature ("jen přečíst, nic neměnit")
- `viewerStore` nebo `uiStore` dostane data, která patří do URL nebo query cache

**Ochrana:** code review checklist vycházející přímo z pravidel tohoto dokumentu. Bez vynucování je governing jen dokument.

### 2. pages/ může přestat být tenká vrstva

`pages/` jsou definovány jako "tenké entry pointy — jen import + compose". Tohle pravidlo drží na začátku, ale časem eroduje přírůstky, které každý sám o sobě vypadají nevinně:

- access check před renderem ("je to jednoduché, patří to sem")
- transformace route param ("zparsuju to tady, v komponentě pak stačí ID")
- složení více queries kvůli loading state
- conditional layout behavior podle query dat

Dohromady vytvoří orchestration vrstvu bez jasného vlastníka.

**Ochrana:** page smí dělat minimální route adaptation — parse `string → number`, handling optional search param, ověření přítomnosti povinného param. Page nesmí dělat business rozhodování, orchestrovat více queries ani obsahovat access logiku. Cokoliv nad tuto hranici patří do feature-level container komponenty.

### 3. features/cases nesmí pohltit sousední features

`cases` je legitimní orchestration root — vlastní case aggregate, `analysis` a `exports` jako subfeatures (žijí uvnitř `cases/`). Riziko je postupná absorpce sousedních features.

Signály, že `cases` začíná bobtnat:

- `cases/` importuje `photos` API hooks přímo (ne přes public API)
- `cases/` importuje `markers` komponenty přímo
- `cases/` začíná obsahovat vlastní reprezentaci work-items nebo estimates

`cases` je přirozený gravitační střed aplikace — do něj se bude chtít "jen dočasně" připojit skoro vše: photo count, marker summaries, work item counters, estimate rollups, timeline side state. Každé takové připojení samo o sobě vypadá rozumně; dohromady z `cases` udělají mega-feature, která ví o všem.

Hranice je jasná: `cases` smí orchestrovat `analysis` a `exports` proto, že jsou to subfeatures (žijí uvnitř `cases/`). `photos`, `markers`, `work-items` a `estimates` jsou souřadné features se svým vlastním public API — `cases` k nim smí sahat pouze přes `features/*/index.ts`, nikdy přes jejich internals.

**Ochrana:** cross-feature import z `cases/` do sousedních features (photos, markers, work-items, estimates) je vždy chyba. Viz pravidlo Cross-feature závislosti.

### 4. Viewer/marker hranice je správná, ale implementačně náročná

`ViewerImageStage` dostává `MarkerOverlay` přes props — architektonicky čisté. Ale viewer potřebuje bohatou interakci:

- marker selection (`activeMarkerId` ve `viewerStore`)
- create mode + draft coords (`viewerStore`)
- hover/highlight stav
- zoom/pan transformace pro overlay positioning

Pokušení při implementaci:

- importovat `useMarkers` přímo do `PhotoViewer` ("jen read, ne coupling")
- přesouvat marker domain data do `viewerStore` ("je to přece viewer stav")
- prop drilling přes 3 vrstvy a pak ho "zkrátit" přímým importem

**Ochrana:**

- `viewerStore` smí držet viewer UI stav (`activeMarkerId`, `isCreateMarkerMode`, `draftMarkerCoords`) — to jsou UI stavy, ne domain data
- marker data (seznam markerů, jejich obsah) fetchuje `PhotoViewerPage` přes `features/markers` public API a předává je jako props do `PhotoViewer` → dál do `ViewerImageStage` → do `MarkerOverlay`; coupling je na úrovni page, ne uvnitř `photos/viewer/`
- `PhotoViewer` a `ViewerImageStage` jsou v tomto ohledu čistě presentačně-orchestrační — dostávají marker data, nic samy nefetchují z jiné feature
- `MarkerOverlay` je čistě presentační — dostává data + callbacks, nic neimportuje

### 5. actorContext.ts a permissions.ts nesmí vstřebat business výjimky

Aktuální stav je správný: `actorContext.ts` řeší identity/context, `permissions.ts` řeší konkrétní akce. Oba jsou čisté funkce s Actor jako argumentem.

Riziko — postupné vrstvení výjimek:

```ts
// Rok 1 — správně
export const canManageCase = (actor: Actor, case: Case) =>
  isSuperAdmin(actor) || actor.organizationId === case.organizationId

// Rok 2 — začíná problém
export const canManageCase = (actor: Actor, case: Case) => {
  if (isSuperAdmin(actor) && isImpersonating(actor)) { … }   // impersonation nuance
  if (case.status === 'archived' && actor.role !== 'manager') { … }  // business exception
  if (tenantHasFeatureFlag(actor, 'advanced_case_mgmt')) { … }  // tenant flag
  …
}
```

**Ochrana:**

- `actorContext.ts`: pouze identity a context (kdo je actor, v jakém kontextu)
- `permissions.ts`: pouze akce (smí X dělat Y?) bez business state výjimek
- case-specific ACL (archived case, locked case) patří do `features/cases`, ne do shared permissions
- tenant feature flags patří do vlastního helperu, ne do permissions

### 6. Interní barrel exporty uvnitř features skrývají dependency hranice

Pravidlo je správně označeno jako "opatrně". Důvod je konkrétní:

```ts
// features/cases/components/index.ts (interní barrel)
export { CaseCard } from "./CaseCard";
export { CaseMetaPanel } from "./CaseMetaPanel";
export { WorkItemCard } from "../work-items/components/WorkItemCard"; // ← neviditelný cross-feature import
```

Jakmile existuje interní barrel, každý import z něj vypadá "lokální" — barrel skrývá skutečný origin. Cross-feature coupling se stane neviditelným.

**Ochrana:**

- veřejný barrel (`features/cases/index.ts`) — ano, to je public API boundary, podléhá review
- interní barrel uvnitř `features/cases/components/` nebo `features/cases/api/` — ne, pokud nevzniká jasný a omezený důvod
- pokud interní barrel vznikne, smí importovat pouze ze stejné feature a podléhá stejně přísnému review jako veřejný `index.ts`

---

## Vynucení

Samotný dokument erozi nezastaví. Pravidla nejsou chyby kompilátoru — porušení jsou tichá. Dvě vrstvy vynucení pokrývají většinu rizik:

### ESLint — import boundaries (vývojářův stroj)

`eslint-plugin-boundaries` nebo `import/no-restricted-paths` zachytí cross-feature porušení před commitem. Deklarativní konfigurace pro `eslint-plugin-boundaries`:

```js
// .eslintrc.js
'boundaries/element-types': ['error', {
  default: 'disallow',
  rules: [
    { from: 'pages',    allow: ['features', 'shared', 'app'] },
    { from: 'features', allow: ['shared'] },   // features nesmí importovat jiné features
    { from: 'app',      allow: ['features', 'shared'] },
    { from: 'shared',   allow: ['shared'] },
    { from: 'store',    allow: ['shared'] },
  ]
}]
```

Zachytí: import mimo `features/*/index.ts`, cross-feature závislosti, import `fetch`/`axios` přímo.

Co zachytí **méně spolehlivě**: re-exporty přes barrel, dynamické importy — pro ty je lepší `dependency-cruiser`.

### dependency-cruiser — CI gate

Spouštěný v CI, zachytí co ESLint přehlédne. Zakázané vztahy se definují deklarativně:

```js
// .dependency-cruiser.cjs
forbidden: [
  {
    name: 'no-cross-feature-internals',
    comment: 'Features smí importovat pouze public API jiné feature (index.ts)',
    severity: 'error',
    from: { path: '^src/features/([^/]+)/' },
    to:   { path: '^src/features/(?!\\1)[^/]+/(?!index\\.ts)' }
  },
  {
    name: 'no-raw-http-in-api-wrappers',
    comment: 'Pouze apiClient, nikdy přímý fetch nebo axios',
    severity: 'error',
    from: { path: '^src/features/.*/api/' },
    to:   { path: '^node_modules/(axios|node-fetch|cross-fetch)' }
  },
  {
    name: 'no-query-invalidation-in-pages',
    comment: 'Pages nesmí volat queryClient.invalidateQueries přímo',
    severity: 'warn',  // warn — nelze odlišit legitimní debug usage
    from: { path: '^src/pages/' },
    to:   { path: '^src/shared/lib/queryClient' }
  }
]
```

### Co nelze automatizovat — vyžaduje code review

| Porušení | Proč nelze automatizovat |
|----------|--------------------------|
| `permissions.ts` business exceptions | ESLint nerozezná identity check od business state check |
| server state ve store | nelze poznat, jestli data "patří" do store nebo do query cache |
| `cases` absorpce přes public API | `import { usePhotos } from 'features/photos'` je formálně povolený import; co se hlídá, je *sémantika* — proč `cases` tu data potřebuje |
| page orchestration creep | složitost page nelze spolehlivě metrifikovat |

Pro tato místa je dostačující code review checklist vycházející ze sekce Implementační rizika. Konkrétní otázky při review:
- Sahá hook na `navigate()` nebo `toast`?
- Volá page `queryClient.invalidateQueries`?
- Přidalo se do `permissions.ts` cokoliv, co závisí na `case.status`, `case.locked` nebo tenant feature flagu?
- Roste `features/cases` o import ze souřadné feature?
