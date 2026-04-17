import { useContext } from 'react'
import { ImpersonationContext } from '../context'
import type { Actor } from 'shared/types/actor.types'

/**
 * Returns the real authenticated actor (from JWT), never the impersonated user.
 *
 * Use this for: audit logging, billing, security-sensitive UI, access control checks
 * that must reflect the actual logged-in person regardless of impersonation.
 *
 * Do NOT use for: normal UI rendering — use useEffectiveActor() instead.
 */
export function useRealActor(): Actor | null {
  const { realActor } = useContext(ImpersonationContext)
  return realActor
}
