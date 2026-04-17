import { useState, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ImpersonationContext,
  type ImpersonationContextValue,
} from 'features/impersonation'
import { useAuthContext } from './AuthProvider'
import type { Actor } from 'shared/types/actor.types'

/**
 * Must be placed inside AuthProvider.
 *
 * Owns: isImpersonating, effectiveActor
 * Reads from AuthProvider: realActor (actor from JWT — never changes during impersonation)
 *
 * On start/stop impersonation: invalidates tenant-scoped queries so stale data
 * from the previous actor doesn't survive the context switch.
 */
export function ImpersonationProvider({ children }: { children: ReactNode }) {
  const { actor: realActor } = useAuthContext()
  const queryClient = useQueryClient()
  const [effectiveActor, setEffectiveActor] = useState<Actor | null>(null)

  const startImpersonation = useCallback(
    (actor: Actor) => {
      setEffectiveActor(actor)
      // Invalidate all queries — previous actor's data must not leak into new context
      void queryClient.invalidateQueries()
    },
    [queryClient],
  )

  const stopImpersonation = useCallback(() => {
    setEffectiveActor(null)
    void queryClient.invalidateQueries()
  }, [queryClient])

  const value: ImpersonationContextValue = {
    realActor,
    effectiveActor,
    isImpersonating: effectiveActor !== null,
    startImpersonation,
    stopImpersonation,
  }

  return (
    <ImpersonationContext.Provider value={value}>
      {children}
    </ImpersonationContext.Provider>
  )
}
