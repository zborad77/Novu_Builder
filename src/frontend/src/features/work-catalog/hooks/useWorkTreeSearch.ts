import { useMemo } from 'react'
import type { WorkTreeLeafIndexItem } from '../config/workTreeSearchIndex'

export type { WorkTreeLeafIndexItem }

export interface ScoredWorkTreeItem extends WorkTreeLeafIndexItem {
  readonly score: number
  readonly allowed: boolean
  readonly recommended: boolean
}

interface UseWorkTreeSearchParams {
  query: string
  index: readonly WorkTreeLeafIndexItem[]
  allowedCodes: ReadonlySet<string>
  recommendedCodes: ReadonlySet<string>
}

interface UseWorkTreeSearchResult {
  results: readonly ScoredWorkTreeItem[]
  isActive: boolean
}

function normalize(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()
}

function computeSearchScore(item: WorkTreeLeafIndexItem, q: string): number {
  const label = normalize(item.label)
  if (label === q) return 4
  if (label.startsWith(q)) return 3
  if (label.includes(q)) return 2
  if (item.keywords.some((kw) => kw.includes(q))) return 1
  return 0
}

function applyOverlayPriority(a: ScoredWorkTreeItem, b: ScoredWorkTreeItem): number {
  if (a.recommended !== b.recommended) {
    return a.recommended ? -1 : 1
  }

  if (a.allowed !== b.allowed) {
    return a.allowed ? -1 : 1
  }

  return 0
}

export function useWorkTreeSearch({
  query,
  index,
  allowedCodes,
  recommendedCodes,
}: UseWorkTreeSearchParams): UseWorkTreeSearchResult {
  const q = normalize(query)

  const results = useMemo((): readonly ScoredWorkTreeItem[] => {
    if (q.length < 2) return []

    const scored: ScoredWorkTreeItem[] = []
    for (const item of index) {
      const score = computeSearchScore(item, q)
      if (score === 0) continue
      scored.push({
        ...item,
        score,
        allowed: allowedCodes.has(item.wtCode),
        recommended: recommendedCodes.has(item.wtCode),
      })
    }

    return scored.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score
      const overlayPriority = applyOverlayPriority(a, b)
      if (overlayPriority !== 0) return overlayPriority
      return a.label.localeCompare(b.label, 'cs')
    })
  }, [q, index, allowedCodes, recommendedCodes])

  return { results, isActive: q.length >= 2 }
}
