import { Link, Outlet } from '@tanstack/react-router'
import { paths } from 'app/router/paths'

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-white/80 bg-white/90 shadow-[0_30px_80px_rgba(15,23,42,0.12)] lg:grid-cols-[1.1fr_0.9fr]">
        <section className="flex flex-col justify-between bg-slate-950 px-8 py-10 text-white sm:px-10">
          <div className="space-y-4">
            <p className="text-xs font-semibold uppercase tracking-[0.36em] text-emerald-300">
              NOVU Builder
            </p>
            <h1 className="max-w-md text-4xl font-semibold leading-tight">
              Web front-end shell pripraveny pro auth flow a dalsi feature vrstvy.
            </h1>
            <p className="max-w-lg text-sm leading-6 text-slate-300">
              Tohle je zakladni vstupni vrstva pro login, reset hesla a dalsi
              neautentizovane obrazovky.
            </p>
          </div>

          <div className="flex flex-wrap gap-3 text-sm text-slate-300">
            <Link
              to={paths.login}
              className="rounded-full border border-white/20 px-4 py-2 transition hover:border-emerald-300 hover:text-white"
            >
              Login
            </Link>
            <Link
              to={paths.forgotPassword}
              className="rounded-full border border-white/20 px-4 py-2 transition hover:border-emerald-300 hover:text-white"
            >
              Forgot Password
            </Link>
            <Link
              to={paths.resetPassword}
              className="rounded-full border border-white/20 px-4 py-2 transition hover:border-emerald-300 hover:text-white"
            >
              Reset Password
            </Link>
          </div>
        </section>

        <section className="flex items-center justify-center bg-[linear-gradient(180deg,rgba(248,250,252,0.96),rgba(241,245,249,0.94))] px-6 py-8 sm:px-8">
          <div className="w-full max-w-md">
            <Outlet />
          </div>
        </section>
      </div>
    </div>
  )
}
