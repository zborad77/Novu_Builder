import type { ReactNode } from 'react'

interface PageScaffoldProps {
  title: string
  description: string
  children?: ReactNode
}

export function PageScaffold({
  title,
  description,
  children,
}: PageScaffoldProps) {
  return (
    <section className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">
        Page Scaffold
      </p>
      <h2 className="mt-3 text-2xl font-semibold text-slate-950">{title}</h2>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
        {description}
      </p>
      {children ? <div className="mt-6">{children}</div> : null}
    </section>
  )
}
