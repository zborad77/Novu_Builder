import { bffAuth, UNAUTHORIZED_EVENT, type LogoutAllResult } from 'shared/lib/apiClient'
import type { LoginResponse, SessionResponse } from '../types/auth.types'

// API vrstva feature auth (NC-007): přihlášení a session jdou přes gateway (/bff/*).
// Žádné tokeny v JS – session nese HttpOnly cookie, CSRF token drží apiClient v paměti.

export function login(email: string, password: string): Promise<LoginResponse> {
  return bffAuth.login(email, password)
}

export function fetchSession(signal?: AbortSignal): Promise<SessionResponse> {
  return bffAuth.getSession(signal ? { signal } : {})
}

export function logout(): Promise<void> {
  return bffAuth.logout()
}

/** `{ partial: true }` = gateway odhlásila, ale revokace v core nebyla potvrzena. */
export function logoutAll(): Promise<LogoutAllResult> {
  return bffAuth.logoutAll()
}

export type { LogoutAllResult }

/** Událost, kterou apiClient vyšle po 401 z /bff/api (session skončila). */
export { UNAUTHORIZED_EVENT }
