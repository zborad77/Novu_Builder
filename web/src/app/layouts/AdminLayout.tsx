import { Link, Outlet } from '@tanstack/react-router'
import { paths } from 'app/router/paths'

const ADMIN_LINKS = [
  { label: 'Companies', to: paths.adminCompanies },
  { label: 'Users', to: paths.adminUsers },
  { label: 'Jobs', to: paths.adminJobs },
  { label: 'Audit', to: paths.adminAudit },
] as const

export function AdminLayout() {
  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600">
          Admin
        </p>
        <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <h1 className="text-3xl font-semibold text-slate-950">
              Admin section shell
            </h1>
            <p className="max-w-2xl text-sm leading-6 text-slate-600">
              Tohle je kostra pro superadmin routy. Guard zustava navazany nad
              real actor kontextem i pri impersonaci.
            </p>
          </div>

          <nav className="flex flex-wrap gap-2">
            {ADMIN_LINKS.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-emerald-300 hover:text-emerald-700"
                activeProps={{
                  className:
                    'rounded-full border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700',
                }}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </section>

      <Outlet />
    </div>
  )
}
