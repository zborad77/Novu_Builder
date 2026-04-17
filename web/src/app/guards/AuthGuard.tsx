import type { ReactNode } from 'react'
import { Navigate } from '@tanstack/react-router'
import { useAuthContext } from 'app/providers/AuthProvider'
import { RoutePendingBoundary } from 'app/router/RoutePendingBoundary'
import { paths } from 'app/router/paths'

/**
 * Redirects to /login if the actor is not authenticated.
 *
 * Waits for auth state resolution (the /auth/me query) before redirecting —
 * a token may exist but the session might be invalid. We never redirect based
 * on token presence alone.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { actor, isLoading } = useAuthContext()

  if (isLoading) return <RoutePendingBoundary />

  if (!actor) return <Navigate to={paths.login} />

  return <>{children}</>
}
