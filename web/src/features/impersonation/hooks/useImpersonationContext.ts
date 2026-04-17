import { useContext } from 'react'
import { ImpersonationContext } from '../context'
import type { ImpersonationContextValue } from '../types/impersonation.types'

/**
 * Full impersonation context — for impersonation UI (banner, admin controls).
 * Returns { isImpersonating, realActor, effectiveActor, startImpersonation, stopImpersonation }.
 *
 * Most components should use useEffectiveActor() or useRealActor() instead.
 * This hook is for components that need to control or display the impersonation state itself.
 */
export function useImpersonationContext(): ImpersonationContextValue {
  return useContext(ImpersonationContext)
}
