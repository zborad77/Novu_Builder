import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient, tokenStorage } from 'shared/lib/apiClient'
import { AUTH_ME_KEY } from 'app/providers/AuthProvider'
import type { Actor } from 'shared/types/actor.types'
import { paths } from 'app/router/paths'

interface LoginApiResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  sessionId: string | null
  user: {
    id: string
    email: string
    fullName: string
    role: Actor['role']
    organizationId: string
    isSuperAdmin: boolean
  }
}

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiClient.post<LoginApiResponse>('/auth/login', { email, password })
      tokenStorage.setTokens({
        accessToken: res.accessToken,
        refreshToken: res.refreshToken,
      })
      const actor: Actor = {
        id: res.user.id,
        email: res.user.email,
        name: res.user.fullName,
        role: res.user.role,
        organizationId: res.user.organizationId,
      }
      queryClient.setQueryData(AUTH_ME_KEY, actor)
      navigate({ to: paths.cases })
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Nesprávný email nebo heslo.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-slate-900">Přihlášení</h2>
        <p className="mt-1 text-sm text-slate-500">Zadejte své přihlašovací údaje</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
            placeholder="admin@novu.cz"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-slate-700">
            Heslo
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
            placeholder="••••••••"
          />
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? 'Přihlašuji…' : 'Přihlásit se'}
        </button>
      </form>
    </div>
  )
}
