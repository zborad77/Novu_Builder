/**
 * React context for impersonation state.
 *
 * Defined here (inside the feature) so that:
 *  - hooks in features/impersonation/hooks/ can import it without going through app/
 *  - app/providers/ImpersonationProvider.tsx imports it via features/impersonation public API
 *    and provides the value
 *
 * Do NOT import this file directly outside this feature — use the hooks from the public API.
 */

import { createContext } from 'react'
import type { ImpersonationContextValue } from './types/impersonation.types'

export const ImpersonationContext = createContext<ImpersonationContextValue>({
  realActor: null,
  effectiveActor: null,
  isImpersonating: false,
  startImpersonation: () => undefined,
  stopImpersonation: () => undefined,
})
