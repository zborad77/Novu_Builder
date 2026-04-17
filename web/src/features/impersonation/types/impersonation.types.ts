import type { Actor } from 'shared/types/actor.types'

export interface ImpersonationContextValue {
  realActor: Actor | null
  effectiveActor: Actor | null
  isImpersonating: boolean
  startImpersonation: (actor: Actor) => void
  stopImpersonation: () => void
}
