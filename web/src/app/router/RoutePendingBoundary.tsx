/**
 * Shared pending/loading component for TanStack Router routes.
 * Used as pendingComponent on route groups that own loading UX.
 */
export function RoutePendingBoundary() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-4 rounded-3xl border border-slate-200/80 bg-white/80 p-8 text-center shadow-sm">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-500" />
      <p className="text-sm text-slate-500">Nacitam route shell...</p>
    </div>
  )
}
