import type { ApiError } from 'shared/types/api.types'
import type { Actor as SharedActor, ActorRole } from 'shared/types/actor.types'

export type { ActorRole }
export type Actor = SharedActor

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  tokenType: 'Bearer'
  expiresIn: number
}

export interface LoginRequest {
  email: string
  password: string
  rememberMe?: boolean
}

export interface LoginResponse {
  accessToken: string
  refreshToken: string
  tokenType: string
  user: Actor
}

export type AuthMeResponse = Actor

export interface Session {
  id: string
  actorId: Actor['id']
  createdAt: string
  lastSeenAt: string
  expiresAt: string | null
  revokedAt: string | null
  ipAddress: string | null
  userAgent: string | null
  isCurrent: boolean
}

export interface SessionsResponse {
  sessions: Session[]
}

export interface RefreshTokenRequest {
  refreshToken: string
}

export interface RefreshTokenResponse {
  accessToken: string
  refreshToken?: string
  tokenType: 'Bearer'
  expiresIn: number
}

export interface LogoutResponse {
  ok: true
}

export interface ForgotPasswordRequest {
  email: string
}

export interface ForgotPasswordResponse {
  ok: true
}

export interface ResetPasswordRequest {
  token: string
  password: string
}

export interface ResetPasswordResponse {
  ok: true
}

export interface ChangePasswordRequest {
  currentPassword: string
  newPassword: string
}

export interface ChangePasswordResponse {
  ok: true
}

export interface RevokeSessionResponse {
  revokedSessionId: Session['id']
}

export interface JwtActorPayload {
  sub: Actor['id']
  email: Actor['email']
  name: string
  role: ActorRole
  organizationId: Actor['organizationId']
  iat: number
  exp: number
}

export type AuthField =
  | 'email'
  | 'password'
  | 'currentPassword'
  | 'newPassword'
  | 'token'

export type AuthErrorCode =
  | 'INVALID_CREDENTIALS'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'ACCOUNT_LOCKED'
  | 'SESSION_EXPIRED'
  | 'SESSION_REVOKED'
  | 'TOKEN_REFRESH_FAILED'
  | 'PASSWORD_RESET_EXPIRED'
  | 'PASSWORD_RESET_INVALID'
  | 'PASSWORD_TOO_WEAK'
  | 'PASSWORD_REUSE_NOT_ALLOWED'
  | 'UNKNOWN'

export interface AuthValidationError {
  field: AuthField
  message: string
}

export interface AuthErrorPayload {
  code: AuthErrorCode
  message: string
  status?: number
  validationErrors?: AuthValidationError[]
}

export interface AuthApiErrorShape extends AuthErrorPayload {
  cause?: ApiError
}
