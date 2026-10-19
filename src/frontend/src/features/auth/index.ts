/**
 * PUBLIC API - features/auth
 *
 * Outside this feature, import auth domain types only from here.
 */

export { fetchCurrentActor, login, LOGOUT_EVENT, tokenStorage } from './api/authApi'

export type {
  Actor,
  ActorRole,
  AuthApiErrorShape,
  AuthErrorCode,
  AuthErrorPayload,
  AuthField,
  AuthMeResponse,
  AuthTokens,
  AuthValidationError,
  ChangePasswordRequest,
  ChangePasswordResponse,
  ForgotPasswordRequest,
  ForgotPasswordResponse,
  JwtActorPayload,
  LoginRequest,
  LoginResponse,
  LogoutResponse,
  RefreshTokenRequest,
  RefreshTokenResponse,
  ResetPasswordRequest,
  ResetPasswordResponse,
  RevokeSessionResponse,
  Session,
  SessionsResponse,
} from './types/auth.types'
