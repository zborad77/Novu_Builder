/**
 * PUBLIC API - features/auth
 *
 * Outside this feature, import auth domain types only from here.
 */

export { fetchSession, login, logout, logoutAll, UNAUTHORIZED_EVENT } from './api/authApi'

export type {
  Actor,
  ActorRole,
  AuthUser,
  LoginRequest,
  LoginResponse,
  SessionResponse,
} from './types/auth.types'
