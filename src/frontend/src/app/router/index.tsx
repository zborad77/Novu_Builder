import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
} from '@tanstack/react-router'
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools'
import { AuthGuard } from 'app/guards/AuthGuard'
import { OrgGuard } from 'app/guards/OrgGuard'
import { AppShell } from 'app/layouts/AppShell'
import { AuthLayout } from 'app/layouts/AuthLayout'
import { CaseLayout } from 'app/layouts/CaseLayout'
import { ArchiveViewerPage } from 'pages/ArchiveViewerPage'
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
import { LoginPage } from 'pages/LoginPage'
import { NotFoundPage } from 'pages/NotFoundPage'
import { PhotoViewerPage } from 'pages/PhotoViewerPage'
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

const routeTree = rootRoute.addChildren([
  indexRoute,
  // D-11 / NC-007 etapa 1: obnova hesla (forgot/reset) se nezobrazuje – core vrací 410;
  // vrátí se v etapě 2. Admin routy z webu odstraněny (NovuAdmin je samostatný).
  authRoute.addChildren([loginRoute]),
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
