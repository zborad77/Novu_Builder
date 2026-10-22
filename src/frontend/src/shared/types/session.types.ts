import type { Actor } from './actor.types'

/**
 * Tvary odpovědí veřejných endpointů gateway (NC-007 kontrakt kap. 2).
 * `user` odpovídá `AuthUserRead` z core.
 */

export type BffUser = Actor & {
  impersonatedBy?: string | null
}

export type BffSessionResponse =
  | {
      authenticated: true
      user: BffUser
      csrfToken: string
      expiresAt: string
      idleExpiresAt: string
    }
  | { authenticated: false }

export interface BffLoginResponse {
  user: BffUser
  csrfToken: string
}
