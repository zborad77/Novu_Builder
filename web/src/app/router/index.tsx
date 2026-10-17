import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import { AdminGuard } from 'app/guards/AdminGuard'
import { AuthGuard } from 'app/guards/AuthGuard'
import { OrgGuard } from 'app/guards/OrgGuard'
import { AdminLayout } from 'app/layouts/AdminLayout'
import { AppShell } from 'app/layouts/AppShell'
import { AuthLayout } from 'app/layouts/AuthLayout'
import { CaseLayout } from 'app/layouts/CaseLayout'
import { AdminAuditPage } from 'pages/AdminAuditPage'
import { ArchiveViewerPage } from 'pages/ArchiveViewerPage'
import { AdminCompaniesPage } from 'pages/AdminCompaniesPage'
import { AdminCompanyDetailPage } from 'pages/AdminCompanyDetailPage'
import { AdminJobsPage } from 'pages/AdminJobsPage'
import { AdminUsersPage } from 'pages/AdminUsersPage'
import { CaseDetailPage } from 'pages/CaseDetailPage'
import { CaseEstimatesPage } from 'pages/CaseEstimatesPage'
import { CaseExportsPage } from 'pages/CaseExportsPage'
import { CaseListPage } from 'pages/CaseListPage'
import { CasePhotosPage } from 'pages/CasePhotosPage'
import { CaseTimelinePage } from 'pages/CaseTimelinePage'
import { CaseWorkItemsPage } from 'pages/CaseWorkItemsPage'
import { CatalogMaterialsPage } from 'pages/CatalogMaterialsPage'
import { CatalogPricebooksPage } from 'pages/CatalogPricebooksPage'
import { CatalogWorkTypesPage } from 'pages/CatalogWorkTypesPage'
import { ForgotPasswordPage } from 'pages/ForgotPasswordPage'
import { LoginPage } from 'pages/LoginPage'
import { NotFoundPage } from 'pages/NotFoundPage'
import { PhotoViewerPage } from 'pages/PhotoViewerPage'
import { ResetPasswordPage } from 'pages/ResetPasswordPage'
import { SettingsProfilePage } from 'pages/SettingsProfilePage'
import { SettingsSuppliersPage } from 'pages/SettingsSuppliersPage'
import { RouteErrorBoundary } from './RouteErrorBoundary'
import { RoutePendingBoundary } from './RoutePendingBoundary'
import { paths } from './paths'

function RootComponent() {
  return (
    <>
      <Outlet />
      {import.meta.env.DEV ? <TanStackRouterDevtools initialIsOpen={false} /> : null}
    </>
  )
}

function ProtectedAppLayout() {
  return (
    <AuthGuard>
      <AppShell />
    </AuthGuard>
  )
}

function OrgScopedLayout() {
  return (
    <OrgGuard>
      <Outlet />
    </OrgGuard>
  )
}

function ProtectedAdminLayout() {
  return (
    <AdminGuard>
      <AdminLayout />
    </AdminGuard>
  )
}

function ProtectedCaseLayout() {
  return (
    <OrgGuard>
      <CaseLayout />
    </OrgGuard>
  )
}

const rootRoute = createRootRoute({
  component: RootComponent,
  notFoundComponent: NotFoundPage,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => redirect({ to: paths.cases, throw: true }),
})

const authRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_auth',
  component: AuthLayout,
  errorComponent: RouteErrorBoundary,
  pendingComponent: RoutePendingBoundary,
})

const loginRoute = createRoute({
  getParentRoute: () => authRoute,
  path: 'login',
  component: LoginPage,
})

const forgotPasswordRoute = createRoute({
  getParentRoute: () => authRoute,
  path: 'forgot-password',
  component: ForgotPasswordPage,
})

const resetPasswordRoute = createRoute({
  getParentRoute: () => authRoute,
  path: 'reset-password',
  component: ResetPasswordPage,
})

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_app',
  component: ProtectedAppLayout,
})

const orgRoute = createRoute({
  getParentRoute: () => appRoute,
  id: '_org',
  component: OrgScopedLayout,
})

const casesRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'cases',
  component: CaseListPage,
})

const caseLayoutRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'cases/$caseId',
  component: ProtectedCaseLayout,
  errorComponent: RouteErrorBoundary,
  pendingComponent: RoutePendingBoundary,
})

const caseOverviewRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: '/',
  component: CaseDetailPage,
})

const casePhotosRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'photos',
  component: CasePhotosPage,
})

const photoViewerRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'photos/$imageId',
  component: PhotoViewerPage,
  errorComponent: RouteErrorBoundary,
  pendingComponent: RoutePendingBoundary,
})

const caseWorkItemsRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'work-items',
  component: CaseWorkItemsPage,
})

const caseEstimatesRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'estimates',
  component: CaseEstimatesPage,
})

const caseExportsRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'exports',
  component: CaseExportsPage,
})

const caseTimelineRoute = createRoute({
  getParentRoute: () => caseLayoutRoute,
  path: 'timeline',
  component: CaseTimelinePage,
})

const archiveViewerRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'archive-viewer',
  component: ArchiveViewerPage,
})

const catalogWorkTypesRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'catalog/work-types',
  component: CatalogWorkTypesPage,
})

const catalogMaterialsRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'catalog/materials',
  component: CatalogMaterialsPage,
})

const catalogPricebooksRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'catalog/pricebooks',
  component: CatalogPricebooksPage,
})

const settingsProfileRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'settings/profile',
  component: SettingsProfilePage,
})

const settingsSuppliersRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: 'settings/suppliers',
  component: SettingsSuppliersPage,
})

const adminRoute = createRoute({
  getParentRoute: () => appRoute,
  path: 'admin',
  component: ProtectedAdminLayout,
  errorComponent: RouteErrorBoundary,
  pendingComponent: RoutePendingBoundary,
})

const adminCompaniesRoute = createRoute({
  getParentRoute: () => adminRoute,
  path: 'companies',
  component: AdminCompaniesPage,
})

const adminCompanyDetailRoute = createRoute({
  getParentRoute: () => adminRoute,
  path: 'companies/$companyId',
  component: AdminCompanyDetailPage,
})

const adminUsersRoute = createRoute({
  getParentRoute: () => adminRoute,
  path: 'users',
  component: AdminUsersPage,
})

const adminJobsRoute = createRoute({
  getParentRoute: () => adminRoute,
  path: 'jobs',
  component: AdminJobsPage,
})

const adminAuditRoute = createRoute({
  getParentRoute: () => adminRoute,
  path: 'audit',
  component: AdminAuditPage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  authRoute.addChildren([loginRoute, forgotPasswordRoute, resetPasswordRoute]),
  appRoute.addChildren([
    orgRoute.addChildren([
      casesRoute,
      archiveViewerRoute,
      caseLayoutRoute.addChildren([
        caseOverviewRoute,
        casePhotosRoute,
        photoViewerRoute,
        caseWorkItemsRoute,
        caseEstimatesRoute,
        caseExportsRoute,
        caseTimelineRoute,
      ]),
      catalogWorkTypesRoute,
      catalogMaterialsRoute,
      catalogPricebooksRoute,
      settingsProfileRoute,
      settingsSuppliersRoute,
    ]),
    adminRoute.addChildren([
      adminCompaniesRoute,
      adminCompanyDetailRoute,
      adminUsersRoute,
      adminJobsRoute,
      adminAuditRoute,
    ]),
  ]),
])

export const router = createRouter({
  routeTree,
  defaultPreload: 'intent',
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
