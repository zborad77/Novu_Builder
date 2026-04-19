import type { StaticWorkTree } from '../config/workTreeConfig'

export interface WorkTreeLeafIndexItem {
  readonly leafId: string
  readonly wtCode: string
  readonly label: string
  readonly path: readonly string[]
  readonly pathLabel: string
  readonly keywords: readonly string[]
}

function stripDiacritics(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

function buildKeywords(...labels: string[]): readonly string[] {
  const set = new Set<string>()
  for (const label of labels) {
    const stripped = stripDiacritics(label)
    set.add(stripped)
    for (const word of stripped.split(/[\s/]+/).filter((w) => w.length > 2)) {
      set.add(word)
    }
  }
  // compound: adjacent pair (elem + leaf) for queries like "oprava komína"
  if (labels.length >= 2) {
    set.add(stripDiacritics(`${labels[labels.length - 2]} ${labels[labels.length - 1]}`))
  }
  return [...set]
}

export function flattenWorkTree(tree: StaticWorkTree): readonly WorkTreeLeafIndexItem[] {
  const items: WorkTreeLeafIndexItem[] = []
  for (const area of tree) {
    for (const elem of area.elements) {
      for (const leaf of elem.interventions) {
        const path = [area.label, elem.label, leaf.label] as const
        items.push({
          leafId: leaf.id,
          wtCode: leaf.wtCode,
          label: leaf.label,
          path,
          pathLabel: path.join(' / '),
          keywords: buildKeywords(area.label, elem.label, leaf.label),
        })
      }
    }
  }
  return items
}
