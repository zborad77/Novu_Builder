import { Link, Outlet } from '@tanstack/react-router'
import {
  ImpersonateBanner,
  useEffectiveActor,
  useRealActor,
} from 'features/impersonation'
import { paths } from 'app/router/paths'
import { isSuperAdmin } from 'shared/lib/actorContext'
import { useUIStore } from 'store/uiStore'

const MAIN_NAV = [
  { label: 'Cases', to: paths.cases },
  { label: 'Work Types', to: paths.catalogWorkTypes },
  { label: 'Materials', to: paths.catalogMaterials },
  { label: 'Pricebooks', to: paths.catalogPricebooks },
  { label: 'Profile', to: paths.settingsProfile },
  { label: 'Suppliers', to: paths.settingsSuppliers },
] as const

const ADMIN_NAV = [
  { label: 'Companies', to: paths.adminCompanies },
  { label: 'Users', to: paths.adminUsers },
  { label: 'Jobs', to: paths.adminJobs },
  { label: 'Audit', to: paths.adminAudit },
] as const

export function AppShell() {
  const effectiveActor = useEffectiveActor()
  const realActor = useRealActor()
  const sidebarOpen = useUIStore((state) => state.sidebarOpen)
  const mobileMenuOpen = useUIStore((state) => state.mobileMenuOpen)
  const toggleSidebar = useUIStore((state) => state.toggleSidebar)
  const setMobileMenuOpen = useUIStore((state) => state.setMobileMenuOpen)

  const showAdminNav = realActor ? isSuperAdmin(realActor) : false

  return (
    <div className="min-h-screen">
      <ImpersonateBanner />

      <div className="flex min-h-screen">
        <aside
          className={[
            'fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-slate-200 bg-slate-950 text-slate-100 shadow-2xl transition-transform lg:static lg:translate-x-0',
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full',
            sidebarOpen ? 'lg:w-72' : 'lg:w-24',
          ].join(' ')}
        >
          <div className="border-b border-white/10 px-5 py-5">
            <p className="text-xs font-semibold uppercase tracking-[0.36em] text-emerald-300">
              NOVU Builder
            </p>
            {sidebarOpen ? (
              <p className="mt-3 text-sm text-slate-300">
                Aplikacni shell pro routovani, auth stav a globalni navigaci.
              </p>
            ) : null}
          </div>

          <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
            <nav className="space-y-2">
              {MAIN_NAV.map((item) => (
                <ShellLink
                  key={item.to}
                  label={item.label}
                  to={item.to}
                  compact={!sidebarOpen}
                  onClick={() => setMobileMenuOpen(false)}
                />
              ))}
            </nav>

            {showAdminNav ? (
              <div className="space-y-2 border-t border-white/10 pt-4">
                {sidebarOpen ? (
                  <p className="px-3 text-xs font-semibold uppercase tracking-[0.28em] text-slate-500">
                    Admin
                  </p>
                ) : null}
                {ADMIN_NAV.map((item) => (
                  <ShellLink
                    key={item.to}
                    label={item.label}
                    to={item.to}
                    compact={!sidebarOpen}
                    onClick={() => setMobileMenuOpen(false)}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </aside>

        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/85 backdrop-blur">
            <div className="flex items-center justify-between gap-4 px-4 py-4 sm:px-6">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={toggleSidebar}
                  className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700"
                >
                  Sidebar
                </button>
                <button
                  type="button"
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="rounded-full border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700 lg:hidden"
                >
                  Menu
                </button>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.26em] text-slate-400">
                    App Shell
                  </p>
                  <p className="text-sm text-slate-600">
                    Router, guardy a layout kostra jsou aktivni.
                  </p>
                </div>
              </div>

              <div className="text-right">
                <p className="text-sm font-semibold text-slate-900">
                  {effectiveActor?.fullName ?? 'Guest'}
                </p>
                <p className="text-xs text-slate-500">
                  {effectiveActor?.email ?? 'No active session'}
                </p>
              </div>
            </div>
          </header>

          <main className="flex-1 px-4 py-6 sm:px-6">
            <div className="mx-auto w-full max-w-7xl">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}

function ShellLink({
  label,
  to,
  compact,
  onClick,
}: {
  label: string
  to: string
  compact: boolean
  onClick: () => void
}) {
  return (
    <Link
      to={to}
      onClick={onClick}
      activeProps={{
        className: 'bg-emerald-500/15 text-emerald-200 border-emerald-400/40',
      }}
      inactiveProps={{
        className:
          'border-transparent text-slate-300 hover:bg-white/5 hover:text-white',
      }}
      className={[
        'flex items-center rounded-2xl border px-3 py-3 text-sm font-medium transition',
        compact ? 'justify-center' : 'justify-start',
      ].join(' ')}
    >
      {compact ? label.slice(0, 1) : label}
    </Link>
  )
}
