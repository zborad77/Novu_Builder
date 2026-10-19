import { useRouter } from '@tanstack/react-router'

/**
 * Shared error component for TanStack Router route groups.
 *
 * Used as errorComponent in:
 *  - case detail + tabs
 *  - viewer
 *  - admin detail panels
 *  - auth routes
 */
export function RouteErrorBoundary({ error }: { error: unknown }) {
  const router = useRouter()

  const message =
    error instanceof Error ? error.message : 'Nastala necekavana chyba.'

  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-red-100 bg-white/90 p-8 text-center shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.24em] text-red-500">
        Route Error
      </p>
      <p className="max-w-md text-sm text-slate-700">{message}</p>
      <button
        onClick={() => {
          void router.invalidate()
        }}
        className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700"
      >
        Zkusit znovu
      </button>
    </div>
  )
}
