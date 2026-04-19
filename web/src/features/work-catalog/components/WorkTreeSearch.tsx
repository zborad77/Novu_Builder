import type { ScoredWorkTreeItem } from '../hooks/useWorkTreeSearch'
import type { WorkTypeSelectHandler } from '../types/workCatalog.types'

interface WorkTreeSearchProps {
  query: string
  onQueryChange: (q: string) => void
  results: readonly ScoredWorkTreeItem[]
  isActive: boolean
  autoFocus?: boolean | undefined
  onSelect?: WorkTypeSelectHandler | undefined
}

export function WorkTreeSearch({
  query,
  onQueryChange,
  results,
  isActive,
  autoFocus = false,
  onSelect,
}: WorkTreeSearchProps) {
  return (
    <div className="space-y-2">
      <input
        type="search"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="Hledat typ prace..."
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 shadow-sm placeholder:text-slate-400 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200"
        autoComplete="off"
        spellCheck={false}
        autoFocus={autoFocus}
      />

      {isActive && results.length === 0 && (
        <p className="px-1 py-2 text-sm text-slate-400">Zadne vysledky pro "{query}".</p>
      )}

      {isActive && results.length > 0 && (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {results.map((item) => (
            <SearchResultItem key={item.leafId} item={item} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </div>
  )
}

interface SearchResultItemProps {
  item: ScoredWorkTreeItem
  onSelect?: WorkTypeSelectHandler | undefined
}

function SearchResultItem({ item, onSelect }: SearchResultItemProps) {
  const breadcrumb = item.path.slice(0, 2).join(' / ')

  return (
    <li>
      <button
        type="button"
        disabled={!item.allowed}
        onClick={
          item.allowed
            ? () => {
                void onSelect?.(item.wtCode)
              }
            : undefined
        }
        className={[
          'flex w-full flex-col gap-1 px-4 py-3 text-left transition',
          item.allowed ? 'hover:bg-slate-50' : 'cursor-not-allowed',
        ].join(' ')}
      >
        <div className="flex items-center gap-2">
          <span
            className={[
              'text-sm font-medium',
              item.allowed ? 'text-slate-800' : 'text-slate-300',
            ].join(' ')}
          >
            {item.label}
          </span>

          {item.recommended && item.allowed && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
              Doporuceno
            </span>
          )}

          {!item.allowed && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-400">
              Nedostupne v teto fazi
            </span>
          )}
        </div>

        <span className="text-xs text-slate-400">{breadcrumb}</span>
      </button>
    </li>
  )
}
