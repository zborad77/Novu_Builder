import { Outlet } from '@tanstack/react-router'

export function CaseLayout() {
  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600">
          Case Workspace
        </p>
        <h1 className="mt-3 text-3xl font-semibold text-slate-950">
          Case layout shell
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Tahle route uz drzi samostatny case shell s vlastnim outlet stromem.
          Detail query, tab nav a meta panel se doplni v dalsim kroku.
        </p>
      </section>

      <Outlet />
    </div>
  )
}
