import type { Actor as SharedActor, ActorRole } from 'shared/types/actor.types'
import type { BffLoginResponse, BffSessionResponse, BffUser } from 'shared/types/session.types'

export type { ActorRole }
export type Actor = SharedActor

/** `AuthUserRead` z core, jak ho vrací gateway. */
export type AuthUser = BffUser

export interface LoginRequest {
  email: string
  password: string
}

/** `POST /bff/auth/login` → 200 `{ user, csrfToken }` (NC-007 kap. 2). */
export type LoginResponse = BffLoginResponse

/** `GET /bff/session` (NC-007 kap. 2). */
export type SessionResponse = BffSessionResponse
