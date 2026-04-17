import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Actor, AuthMeResponse } from 'features/auth'
import { apiClient, tokenStorage, LOGOUT_EVENT } from 'shared/lib/apiClient'

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

interface AuthContextValue {
  /** The real authenticated actor from JWT. Never the impersonated user. */
  actor: Actor | null
  isLoading: boolean
  isAuthenticated: boolean
  /** Clears tokens and resets auth state — call after logout mutation. */
  logout: () => void
}

const AuthContext = createContext<AuthContextValue>({
  actor: null,
  isLoading: true,
  isAuthenticated: false,
  logout: () => undefined,
})

export function useAuthContext(): AuthContextValue {
  return useContext(AuthContext)
}

// ---------------------------------------------------------------------------
// Query key (local to app layer, not a feature key factory)
// ---------------------------------------------------------------------------

export const AUTH_ME_KEY = ['auth', 'me'] as const

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const logout = useCallback(() => {
    tokenStorage.clear()
    queryClient.removeQueries({ queryKey: AUTH_ME_KEY })
  }, [queryClient])

  // Listen for logout events dispatched by apiClient (refresh failure)
  useEffect(() => {
    const handler = () => logout()
    window.addEventListener(LOGOUT_EVENT, handler)
    return () => window.removeEventListener(LOGOUT_EVENT, handler)
  }, [logout])

  const { data: actor, isLoading } = useQuery({
    queryKey: AUTH_ME_KEY,
    queryFn: (): Promise<AuthMeResponse> => apiClient.get<AuthMeResponse>('/auth/me'),
    enabled: tokenStorage.getAccess() !== null,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 min — actor data changes rarely
  })

  const value: AuthContextValue = {
    actor: actor ?? null,
    isLoading,
    isAuthenticated: actor !== undefined,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
