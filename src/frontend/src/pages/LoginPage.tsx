import { type FormEvent, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useAuthContext } from 'app/providers/AuthProvider'
import { paths } from 'app/router/paths'
import { t } from 'shared/i18n'
import { ApiError } from 'shared/types'

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return t('auth.login.invalidCredentials')
    if (err.status === 429) return t('auth.login.rateLimited')
  }
  return t('auth.login.failed')
}

export function LoginPage() {
  const navigate = useNavigate()
  const { login, logoutReason } = useAuthContext()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      // Session nese HttpOnly cookie od gateway; v JS žádný token neukládáme.
      await login(email, password)
      void navigate({ to: paths.cases })
    } catch (err: unknown) {
      setError(loginErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-slate-900">{t('auth.login.title')}</h2>
        <p className="mt-1 text-sm text-slate-500">{t('auth.login.subtitle')}</p>
      </div>

      <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
        {logoutReason === 'expired' && !error && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {t('auth.sessionExpired')}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label htmlFor="email" className="block text-sm font-medium text-slate-700">
            {t('auth.login.email')}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            placeholder={t('auth.login.emailPlaceholder')}
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 shadow-sm outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>

        <div className="space-y-1">
          {/* Odkaz „Zapomenuté heslo?“ skrytý: obnova hesla až v etapě 2 (core vrací 410). */}
          <div className="flex items-center justify-between">
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">
              {t('auth.login.password')}
            </label>
          </div>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            placeholder="••••••••••"
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder-slate-400 shadow-sm outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </div>

        <button
          type="submit"
          disabled={loading || !email || !password}
          className="flex w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? t('auth.login.submitting') : t('auth.login.submit')}
        </button>
      </form>
    </div>
  )
}
