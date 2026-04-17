import type { ReactNode } from 'react'
import { Navigate } from '@tanstack/react-router'
import { useAuthContext } from 'app/providers/AuthProvider'
import { RoutePendingBoundary } from 'app/router/RoutePendingBoundary'
import { paths } from 'app/router/paths'
import { canAccessOrgScopedRoute } from 'shared/lib/actorContext'

/**
 * Redirects if the actor has no organizationId AND is not a superadmin.
 *
 * Superadmins are allowed on org-scoped routes even without organizationId —
 * they see all tenants or a specific one when impersonating.
 * Uses actorContext.canAccessOrgScopedRoute() which encodes this exception.
 */
export function OrgGuard({ children }: { children: ReactNode }) {
  const { actor, isLoading } = useAuthContext()

  if (isLoading) return <RoutePendingBoundary />

  if (!actor || !canAccessOrgScopedRoute(actor)) {
    return <Navigate to={paths.login} />
  }

  return <>{children}</>
}
