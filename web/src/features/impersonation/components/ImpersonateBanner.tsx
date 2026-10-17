import { useImpersonationContext } from '../hooks/useImpersonationContext'

/**
 * Visible banner shown globally (in AppShell) during impersonation.
 * Renders nothing when not impersonating.
 */
export function ImpersonateBanner() {
  const { isImpersonating, effectiveActor, stopImpersonation } = useImpersonationContext()

  if (!isImpersonating || !effectiveActor) return null

  return (
    <div className="flex items-center justify-between bg-amber-500 px-4 py-2 text-sm font-medium text-white">
      <span>
        Impersonujete uživatele: <strong>{effectiveActor.fullName}</strong> ({effectiveActor.email})
      </span>
      <button
        onClick={stopImpersonation}
        className="ml-4 rounded border border-white/60 px-3 py-0.5 text-xs hover:bg-white/20"
      >
        Ukončit impersonaci
      </button>
    </div>
  )
}
