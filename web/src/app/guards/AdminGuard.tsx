import type { ReactNode } from 'react'
import { Navigate } from '@tanstack/react-router'
import { useAuthContext } from 'app/providers/AuthProvider'
import { RoutePendingBoundary } from 'app/router/RoutePendingBoundary'
import { paths } from 'app/router/paths'
import { isSuperAdmin } from 'shared/lib/actorContext'

/**
 * Redirects to /cases if the real actor is not a superadmin.
 *
 * IMPORTANT: decision is made over realActor, NOT effectiveActor.
 * A superadmin impersonating a regular user must not lose access to the admin panel.
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const { actor, isLoading } = useAuthContext()

  if (isLoading) return <RoutePendingBoundary />

  if (!actor || !isSuperAdmin(actor)) return <Navigate to={paths.cases} />

  return <>{children}</>
}
