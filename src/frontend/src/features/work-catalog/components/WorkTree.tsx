/**
 * Pure presentational work-type tree.
 *
 * CONTRACT — structural rule enforced by API shape:
 *   - `tree: StaticWorkTree` — branded type; a filtered/mapped result cannot
 *     be passed here without an explicit `as unknown as StaticWorkTree` cast,
 *     which is a visible violation in code review.
 *   - All leaves are always rendered; none are hidden or removed.
 *   - `allowedCodes` / `recommendedCodes` are visual overlays only:
 *       recommended  → badge + highlight
 *       allowed      → enabled button
 *       not allowed  → disabled button (never hidden)
 */
import { useState } from 'react'
import type { StaticWorkTree, WorkTreeLeaf } from '../config/workTreeConfig'
import type { WorkTypeSelectHandler } from '../types/workCatalog.types'

interface WorkTreeProps {
  tree: StaticWorkTree
  allowedCodes: ReadonlySet<string>
  recommendedCodes: ReadonlySet<string>
  onSelect?: WorkTypeSelectHandler | undefined
}

export function WorkTree({ tree, allowedCodes, recommendedCodes, onSelect }: WorkTreeProps) {
  const [openAreas, setOpenAreas] = useState<ReadonlySet<string>>(
    () => new Set(tree.map((a) => a.id)),
  )

  function toggleArea(id: string) {
    setOpenAreas((prev) => {
      const next = new Set(prev)

      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }

      return next
    })
  }

  return (
    <div className="space-y-3">
      {tree.map((area) => {
        const isOpen = openAreas.has(area.id)
        return (
          <section key={area.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <button
              type="button"
              onClick={() => toggleArea(area.id)}
              className="flex w-full items-center justify-between px-5 py-3 text-left"
            >
              <span className="text-sm font-semibold text-slate-800">{area.label}</span>
              <span className="text-xs text-slate-400">{isOpen ? '▲' : '▼'}</span>
            </button>

            {isOpen && (
              <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-4">
                {area.elements.map((elem) => (
                  <div key={elem.id}>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                      {elem.label}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {elem.interventions.map((leaf) => (
                        <LeafButton
                          key={leaf.id}
                          leaf={leaf}
                          allowed={allowedCodes.has(leaf.wtCode)}
                          recommended={recommendedCodes.has(leaf.wtCode)}
                          onSelect={onSelect}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}

interface LeafButtonProps {
  leaf: WorkTreeLeaf
  allowed: boolean
  recommended: boolean
  onSelect?: WorkTypeSelectHandler | undefined
}

function LeafButton({ leaf, allowed, recommended, onSelect }: LeafButtonProps) {
  return (
    <button
      type="button"
      disabled={!allowed}
      onClick={
        allowed
          ? () => {
              void onSelect?.(leaf.wtCode)
            }
          : undefined
      }
      className={[
        'rounded-full border px-3 py-1 text-xs font-medium transition',
        allowed
          ? recommended
            ? 'border-emerald-300 bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200 hover:bg-emerald-100'
            : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
          : 'cursor-not-allowed border-slate-100 bg-slate-50 text-slate-300',
      ].join(' ')}
      title={!allowed ? 'Nedostupné v aktuální fázi případu' : undefined}
    >
      {leaf.label}
      {recommended && allowed ? (
        <span className="ml-1.5 text-emerald-500">★</span>
      ) : null}
    </button>
  )
}
