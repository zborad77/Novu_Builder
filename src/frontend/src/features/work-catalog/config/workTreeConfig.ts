/**
 * Static UI tree config: area → element → intervention.
 * Each leaf's wtCode maps to a flat work type code in the backend catalog.
 * The tree is UI-only — the backend always works with flat wtCode values.
 *
 * Structural contract:
 *   - All interfaces are deeply readonly — the tree must not be mutated.
 *   - `StaticWorkTree` is a branded type. `WORK_TREE.filter(...)` returns
 *     `WorkTreeArea[]` which is NOT assignable to `StaticWorkTree`, making
 *     accidental structural transformation a compile-time error.
 *   - Components must accept `StaticWorkTree`, not `WorkTreeArea[]`.
 */

export interface WorkTreeLeaf {
  readonly id: string
  readonly label: string
  readonly wtCode: string
}

export interface WorkTreeElement {
  readonly id: string
  readonly label: string
  readonly interventions: readonly WorkTreeLeaf[]
}

export interface WorkTreeArea {
  readonly id: string
  readonly label: string
  readonly elements: readonly WorkTreeElement[]
}

// Branded type — prevents passing filter/map/sort results as `tree` prop.
declare const _staticWorkTreeBrand: unique symbol
export type StaticWorkTree = readonly WorkTreeArea[] & { readonly [_staticWorkTreeBrand]: true }

export const WORK_TREE = [
  // ────────────────────────────────────────────────────────────────────────
  // STŘECHA / Roof
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_roof",
    label: "Střecha",
    elements: [
      {
        id: "elem_roof_cover",
        label: "Střešní krytina",
        interventions: [
          { id: "roof_cover_repair",        label: "Oprava",        wtCode: "roof-repair" },
          { id: "roof_cover_installation",  label: "Montáž",        wtCode: "roof-cover-installation" },
          { id: "roof_cover_replacement",   label: "Výměna",        wtCode: "roof-cover-replacement" },
          { id: "roof_cover_cleaning",      label: "Čištění",       wtCode: "roof-cover-cleaning" },
        ],
      },
      {
        id: "elem_roof_truss",
        label: "Krov / konstrukce",
        interventions: [
          { id: "roof_truss_new",            label: "Nový krov",        wtCode: "roof-truss-new" },
          { id: "roof_truss_repair",         label: "Oprava krovu",     wtCode: "roof-truss-repair" },
          { id: "roof_truss_reconstruction", label: "Rekonstrukce",     wtCode: "roof-truss-reconstruction" },
          { id: "roof_truss_reinforcement",  label: "Zesílení / sanace",wtCode: "roof-truss-reinforcement" },
        ],
      },
      {
        id: "elem_roof_insulation",
        label: "Střešní izolace",
        interventions: [
          { id: "roof_insulation_new",         label: "Nová izolace",  wtCode: "roof-insulation" },
          { id: "roof_insulation_repair",      label: "Oprava izolace",wtCode: "roof-insulation-repair" },
          { id: "roof_insulation_replacement", label: "Výměna izolace",wtCode: "roof-insulation-replacement" },
        ],
      },
      {
        id: "elem_gutters",
        label: "Okapy / svody",
        interventions: [
          { id: "gutter_installation", label: "Montáž",   wtCode: "gutter-installation" },
          { id: "gutter_repair",       label: "Oprava",   wtCode: "gutter-repair" },
          { id: "gutter_replacement",  label: "Výměna",   wtCode: "gutter-replacement" },
          { id: "gutter_cleaning",     label: "Čištění",  wtCode: "gutter-cleaning" },
        ],
      },
      {
        id: "elem_skylights",
        label: "Střešní okna / světlíky",
        interventions: [
          { id: "skylight_installation", label: "Montáž",   wtCode: "skylight-installation" },
          { id: "skylight_repair",       label: "Oprava",   wtCode: "skylight-repair" },
          { id: "skylight_replacement",  label: "Výměna",   wtCode: "skylight-replacement" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // FASÁDA / Facade
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_facade",
    label: "Fasáda",
    elements: [
      {
        id: "elem_facade_plaster",
        label: "Omítka fasády",
        interventions: [
          { id: "facade_plaster_repair",         label: "Oprava",       wtCode: "facade-plaster-repair" },
          { id: "facade_plaster_reconstruction", label: "Rekonstrukce", wtCode: "facade-plaster-reconstruction" },
        ],
      },
      {
        id: "elem_facade_insulation",
        label: "Zateplení fasády",
        interventions: [
          { id: "facade_insulation_new",            label: "Nové zateplení", wtCode: "insulation-installation" },
          { id: "facade_insulation_repair",         label: "Oprava",         wtCode: "facade-insulation-repair" },
          { id: "facade_insulation_reconstruction", label: "Rekonstrukce",   wtCode: "facade-insulation-reconstruction" },
        ],
      },
      {
        id: "elem_facade_coating",
        label: "Nátěr / obklad fasády",
        interventions: [
          { id: "facade_coating_new",     label: "Nový nátěr / obklad", wtCode: "facade-installation" },
          { id: "facade_coating_renewal", label: "Obnova nátěru",       wtCode: "facade-coating-renewal" },
        ],
      },
      {
        id: "elem_facade_cracks",
        label: "Trhliny ve fasádě",
        interventions: [
          { id: "facade_crack_repair",       label: "Lokální oprava trhlin",wtCode: "facade-crack-repair" },
          { id: "facade_crack_remediation",  label: "Komplexní sanace",     wtCode: "facade-crack-remediation" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // KOMÍN / Chimney
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_chimney",
    label: "Komín",
    elements: [
      {
        id: "elem_chimney_body",
        label: "Těleso komína",
        interventions: [
          { id: "chimney_body_rebuild",  label: "Přestavba / renovace",wtCode: "chimney-renovation" },
          { id: "chimney_body_new",      label: "Nový komín",           wtCode: "chimney-new-build" },
          { id: "chimney_body_repair",   label: "Oprava zdiva",         wtCode: "chimney-body-repair" },
          { id: "chimney_body_removal",  label: "Demolice / odstranění",wtCode: "chimney-body-removal" },
        ],
      },
      {
        id: "elem_chimney_lining",
        label: "Vložkování / průduch",
        interventions: [
          { id: "chimney_lining_installation", label: "Vložkování — nové",  wtCode: "chimney-lining-installation" },
          { id: "chimney_lining_replacement",  label: "Vložkování — výměna",wtCode: "chimney-lining-replacement" },
          { id: "chimney_lining_repair",       label: "Oprava průduchu",    wtCode: "chimney-lining-repair" },
        ],
      },
      {
        id: "elem_chimney_plaster",
        label: "Omítka komína",
        interventions: [
          { id: "chimney_plaster_new",    label: "Nová omítka", wtCode: "chimney-plaster-new" },
          { id: "chimney_plaster_repair", label: "Oprava",      wtCode: "chimney-plaster-repair" },
        ],
      },
      {
        id: "elem_chimney_head",
        label: "Hlava komína",
        interventions: [
          { id: "chimney_head_repair",           label: "Oprava hlavy",             wtCode: "chimney-head-repair" },
          { id: "chimney_head_reconstruction",   label: "Rekonstrukce hlavy",       wtCode: "chimney-head-reconstruction" },
          { id: "chimney_head_cap_installation", label: "Montáž komínové čepičky", wtCode: "chimney-head-cap-installation" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // OKNA A DVEŘE / Windows & Doors
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_windows_doors",
    label: "Okna a dveře",
    elements: [
      {
        id: "elem_windows",
        label: "Okna",
        interventions: [
          { id: "window_installation", label: "Montáž nových oken", wtCode: "window-installation" },
          { id: "window_replacement",  label: "Výměna oken",         wtCode: "window-replacement" },
          { id: "window_repair",       label: "Oprava okna",         wtCode: "window-repair" },
          { id: "window_adjustment",   label: "Seřízení oken",       wtCode: "window-adjustment" },
        ],
      },
      {
        id: "elem_doors",
        label: "Dveře",
        interventions: [
          { id: "door_installation", label: "Montáž nových dveří", wtCode: "door-installation" },
          { id: "door_replacement",  label: "Výměna dveří",         wtCode: "door-replacement" },
          { id: "door_repair",       label: "Oprava dveří",         wtCode: "door-repair" },
        ],
      },
      {
        id: "elem_sealing",
        label: "Těsnění / parapety",
        interventions: [
          { id: "sealing_installation", label: "Montáž těsnění / parapetů", wtCode: "sealing-installation" },
          { id: "sealing_replacement",  label: "Výměna těsnění",             wtCode: "sealing-replacement" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // BALKON / TERASA / Balcony-Terrace
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_balcony_terrace",
    label: "Balkon / terasa",
    elements: [
      {
        id: "elem_balcony_waterproofing",
        label: "Hydroizolace",
        interventions: [
          { id: "balcony_waterproofing_new",            label: "Nová hydroizolace",   wtCode: "balcony-waterproofing-new" },
          { id: "balcony_waterproofing_repair",         label: "Oprava hydroizolace", wtCode: "balcony-waterproofing-repair" },
          { id: "balcony_waterproofing_reconstruction", label: "Rekonstrukce",        wtCode: "balcony-waterproofing-reconstruction" },
        ],
      },
      {
        id: "elem_balcony_surface",
        label: "Povrch balkonu / terasy",
        interventions: [
          { id: "balcony_surface_installation", label: "Nový povrch",  wtCode: "balcony-surface-installation" },
          { id: "balcony_surface_repair",       label: "Oprava",       wtCode: "balcony-surface-repair" },
          { id: "balcony_surface_replacement",  label: "Výměna",       wtCode: "balcony-surface-replacement" },
        ],
      },
      {
        id: "elem_balcony_railing",
        label: "Zábradlí",
        interventions: [
          { id: "balcony_railing_installation", label: "Montáž zábradlí", wtCode: "balcony-railing-installation" },
          { id: "balcony_railing_repair",       label: "Oprava zábradlí", wtCode: "balcony-railing-repair" },
          { id: "balcony_railing_replacement",  label: "Výměna zábradlí", wtCode: "balcony-railing-replacement" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // ZÁKLADY / Foundation
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_foundation",
    label: "Základy",
    elements: [
      {
        id: "elem_foundation_waterproofing",
        label: "Hydroizolace základů",
        interventions: [
          { id: "foundation_waterproofing_new",    label: "Nová hydroizolace", wtCode: "foundation-waterproofing-new" },
          { id: "foundation_waterproofing_repair",  label: "Oprava",           wtCode: "foundation-waterproofing-repair" },
        ],
      },
      {
        id: "elem_foundation_masonry",
        label: "Zdivo základů",
        interventions: [
          { id: "foundation_masonry_repair",       label: "Oprava zdiva",          wtCode: "foundation-masonry-repair" },
          { id: "foundation_moisture_remediation", label: "Sanace vlhkosti",       wtCode: "foundation-moisture-remediation" },
        ],
      },
      {
        id: "elem_foundation_drainage",
        label: "Drenáž",
        interventions: [
          { id: "foundation_drainage_installation", label: "Nová drenáž",   wtCode: "foundation-drainage-installation" },
          { id: "foundation_drainage_repair",       label: "Oprava drenáže",wtCode: "foundation-drainage-repair" },
        ],
      },
    ],
  },

  // ────────────────────────────────────────────────────────────────────────
  // INTERIÉR / Interior
  // ────────────────────────────────────────────────────────────────────────
  {
    id: "area_interior",
    label: "Interiér",
    elements: [
      {
        id: "elem_interior_walls",
        label: "Stěny",
        interventions: [
          { id: "interior_wall_repair",        label: "Oprava stěn",        wtCode: "interior-wall-repair" },
          { id: "interior_wall_painting",      label: "Malba / nátěr",      wtCode: "painting" },
          { id: "interior_wall_plastering",    label: "Omítkářské práce",   wtCode: "plastering" },
          { id: "interior_wall_drywall",       label: "SDK příčky / desky", wtCode: "drywall-installation" },
        ],
      },
      {
        id: "elem_interior_floor",
        label: "Podlahy",
        interventions: [
          { id: "interior_floor_installation", label: "Nová podlaha",      wtCode: "interior-floor-installation" },
          { id: "interior_floor_replacement",  label: "Výměna podlahy",    wtCode: "interior-floor-replacement" },
          { id: "interior_floor_renovation",   label: "Renovace podlahy",  wtCode: "floor-renovation" },
        ],
      },
      {
        id: "elem_interior_ceiling",
        label: "Stropy",
        interventions: [
          { id: "interior_ceiling_repair",     label: "Oprava stropu",     wtCode: "interior-ceiling-repair" },
          { id: "interior_ceiling_lowering",   label: "Snížení stropu",    wtCode: "interior-ceiling-lowering" },
          { id: "interior_ceiling_finishing",  label: "Dokončovací práce", wtCode: "interior-finishing" },
        ],
      },
    ],
  },
] as unknown as StaticWorkTree

// ────────────────────────────────────────────────────────────────────────────
// Lookup helpers
// ────────────────────────────────────────────────────────────────────────────

/** Flat map: leafId → wtCode */
export const LEAF_ID_TO_WT_CODE: Record<string, string> = Object.fromEntries(
  WORK_TREE.flatMap(area =>
    area.elements.flatMap(elem =>
      elem.interventions.map(leaf => [leaf.id, leaf.wtCode])
    )
  )
)

/** Flat map: wtCode → leaf (first match — codes are unique per tree contract) */
export const WT_CODE_TO_LEAF: Record<string, WorkTreeLeaf & { areaId: string; elemId: string }> =
  Object.fromEntries(
    WORK_TREE.flatMap(area =>
      area.elements.flatMap(elem =>
        elem.interventions.map(leaf => [
          leaf.wtCode,
          { ...leaf, areaId: area.id, elemId: elem.id },
        ])
      )
    )
  )

/** Return the tree path label for a given wtCode, e.g. "Střecha › Okapy / svody › Oprava" */
export function getTreePathLabel(wtCode: string): string | null {
  const entry = WT_CODE_TO_LEAF[wtCode]
  if (!entry) return null
  const area = WORK_TREE.find(a => a.id === entry.areaId)
  const elem = area?.elements.find(e => e.id === entry.elemId)
  if (!area || !elem) return null
  return `${area.label} › ${elem.label} › ${entry.label}`
}
