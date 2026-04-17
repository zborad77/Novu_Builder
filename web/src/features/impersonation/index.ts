/**
 * PUBLIC API — features/impersonation
 *
 * Import only from here outside this feature.
 * The ImpersonationContext is exported so that app/providers/ImpersonationProvider
 * can use it as the context provider value carrier.
 */

export { ImpersonationContext } from './context'
export type { ImpersonationContextValue } from './types/impersonation.types'

export { useEffectiveActor } from './hooks/useEffectiveActor'
export { useRealActor } from './hooks/useRealActor'
export { useImpersonationContext } from './hooks/useImpersonationContext'

export { ImpersonateBanner } from './components/ImpersonateBanner'
