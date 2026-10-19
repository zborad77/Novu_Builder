import { useContext } from 'react'
import { ImpersonationContext } from '../context'
import type { Actor } from 'shared/types/actor.types'

/**
 * Returns the effective actor for normal UI rendering:
 *  - When impersonating: the impersonated user
 *  - Otherwise: the real logged-in actor
 *
 * Use this for: displaying user name, checking UI permissions, rendering scoped data.
 * Do NOT use for: audit logging, billing, security checks — use useRealActor() instead.
 */
export function useEffectiveActor(): Actor | null {
  const { effectiveActor, realActor } = useContext(ImpersonationContext)
  return effectiveActor ?? realActor
}
