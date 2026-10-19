import { apiClient, tokenStorage, LOGOUT_EVENT } from 'shared/lib/apiClient'
import type { AuthMeResponse, LoginResponse } from '../types/auth.types'

// API vrstva feature auth: stránky a providery nevolají apiClient přímo.
export function login(email: string, password: string): Promise<LoginResponse> {
  return apiClient.post<LoginResponse>('/auth/login', { email, password })
}

export function fetchCurrentActor(): Promise<AuthMeResponse> {
  return apiClient.get<AuthMeResponse>('/auth/me')
}

export { tokenStorage, LOGOUT_EVENT }
