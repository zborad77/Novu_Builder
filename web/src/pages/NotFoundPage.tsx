import { Link } from '@tanstack/react-router'
import { paths } from 'app/router/paths'

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4 py-10">
      <section className="w-full max-w-xl rounded-[2rem] border border-slate-200/80 bg-white/90 p-8 text-center shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-rose-500">
          404
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-950">
          Route nenalezena
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Tahle cesta jeste nema prirazeny page entrypoint nebo je URL neplatna.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            to={paths.cases}
            className="rounded-full bg-slate-950 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Otevrit cases
          </Link>
          <Link
            to={paths.login}
            className="rounded-full border border-slate-200 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700"
          >
            Otevrit login
          </Link>
        </div>
      </section>
    </div>
  )
}
