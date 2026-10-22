import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import type { Actor, SessionResponse } from 'features/auth'
import {
  fetchSession,
  login as loginRequest,
  logout as logoutRequest,
  logoutAll as logoutAllRequest,
  UNAUTHORIZED_EVENT,
} from 'features/auth'

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

/** Proč uživatel skončil odhlášený – login stránka podle toho zobrazí hlášku. */
export type LogoutReason = 'expired' | null

interface AuthContextValue {
  /** Přihlášený uživatel podle `GET /bff/session`. */
  actor: Actor | null
  isLoading: boolean
  /** Session se nepodařilo ověřit (gateway nedostupná, 5xx, 503). */
  isError: boolean
  isAuthenticated: boolean
  logoutReason: LogoutReason
  /** Znovu načte `/bff/session`. */
  retry: () => void
  /** `POST /bff/auth/login`; při chybě vyhodí ApiError. */
  login: (email: string, password: string) => Promise<void>
  /** `POST /bff/auth/logout`. */
  logout: () => Promise<void>
  /** `POST /bff/auth/logout-all` – odhlásí všechny webové sessions uživatele. */
  logoutAll: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue>({
  actor: null,
  isLoading: true,
  isError: false,
  isAuthenticated: false,
  logoutReason: null,
  retry: () => undefined,
  login: () => Promise.resolve(),
  logout: () => Promise.resolve(),
  logoutAll: () => Promise.resolve(),
})

export function useAuthContext(): AuthContextValue {
  return useContext(AuthContext)
}

// ---------------------------------------------------------------------------
// Query key (local to app layer, not a feature key factory)
// ---------------------------------------------------------------------------

export const AUTH_SESSION_KEY = ['auth', 'session'] as const

const LOGGED_OUT: SessionResponse = { authenticated: false }

/** Zahodí data všech ostatních dotazů – nesmí přežít do další session. */
function clearUserData(queryClient: QueryClient): void {
  const isNotSession = (query: { queryKey: readonly unknown[] }) =>
    query.queryKey[0] !== AUTH_SESSION_KEY[0]
  void queryClient.cancelQueries({ predicate: isNotSession })
  queryClient.removeQueries({ predicate: isNotSession })
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [logoutReason, setLogoutReason] = useState<LogoutReason>(null)

  const markLoggedOut = useCallback(
    (reason: LogoutReason) => {
      setLogoutReason(reason)
      queryClient.setQueryData(AUTH_SESSION_KEY, LOGGED_OUT)
      clearUserData(queryClient)
    },
    [queryClient],
  )

  // apiClient hlásí 401 z /bff/api → session skončila (idle/absolutní limit, revokace).
  useEffect(() => {
    const handler = () => markLoggedOut('expired')
    window.addEventListener(UNAUTHORIZED_EVENT, handler)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler)
  }, [markLoggedOut])

  const sessionQuery = useQuery({
    queryKey: AUTH_SESSION_KEY,
    queryFn: ({ signal }): Promise<SessionResponse> => fetchSession(signal),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const login = useCallback(
    async (email: string, password: string) => {
      await loginRequest(email, password)
      setLogoutReason(null)
      clearUserData(queryClient)
      // Načte úplný stav session (expirace, aktuální CSRF token).
      await queryClient.invalidateQueries({ queryKey: AUTH_SESSION_KEY })
    },
    [queryClient],
  )

  const logout = useCallback(async () => {
    await logoutRequest()
    markLoggedOut(null)
  }, [markLoggedOut])

  const logoutAll = useCallback(async () => {
    await logoutAllRequest()
    markLoggedOut(null)
  }, [markLoggedOut])

  const { refetch } = sessionQuery
  const retry = useCallback(() => {
    void refetch()
  }, [refetch])

  const session = sessionQuery.data
  const actor = session?.authenticated ? session.user : null

  const value: AuthContextValue = {
    actor,
    isLoading: sessionQuery.isLoading,
    isError: sessionQuery.isError && session === undefined,
    isAuthenticated: actor !== null,
    logoutReason,
    retry,
    login,
    logout,
    logoutAll,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
