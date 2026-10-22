import type { ReactNode } from 'react'
import { Navigate } from '@tanstack/react-router'
import { useAuthContext } from 'app/providers/AuthProvider'
import { RoutePendingBoundary } from 'app/router/RoutePendingBoundary'
import { paths } from 'app/router/paths'
import { t } from 'shared/i18n'

/**
 * Redirects to /login if the actor is not authenticated.
 *
 * Stav přihlášení je jen to, co vrátí gateway z `GET /bff/session` (HttpOnly
 * cookie, v JS žádný token). Když se session nepodaří ověřit (gateway/core
 * nedostupné), nepřesměrováváme na login, ale nabídneme opakování.
 */
export function AuthGuard({ children }: { children: ReactNode }) {
  const { actor, isLoading, isError, retry } = useAuthContext()

  if (isLoading) return <RoutePendingBoundary />

  if (isError) {
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-red-100 bg-white/90 p-8 text-center shadow-sm">
        <p className="max-w-md text-sm text-slate-700">{t('auth.session.error')}</p>
        <button
          type="button"
          onClick={retry}
          className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
        >
          {t('common.retry')}
        </button>
      </div>
    )
  }

  if (!actor) return <Navigate to={paths.login} />

  return <>{children}</>
}
