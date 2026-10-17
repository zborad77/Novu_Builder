# PR Review Checklist — Web Frontend

Rychlá kontrola při každém review. Automatika (ESLint + dep-cruiser) chytí hranice importů;
níže jsou věci, které nelze automatizovat.

---

## Importy a vrstvení

- [ ] Importy **z jiné feature** jdou přes `features/<name>/index.ts` — žádný import z interní cesty (`features/cases/components/CaseCard` je chyba). Uvnitř stejné feature jsou přímé importy v pořádku.
- [ ] `*Api.ts` soubory importují jen `apiClient` z `shared/lib/apiClient` — žádný přímý `axios` ani `fetch`.
- [ ] `shared/` nezávisí na `features/`, `pages/`, `app/` ani `store/`.
- [ ] Žádné nové kruhové závislosti (dep-cruiser rule `no-circular`).

## Pages — tenká vrstva

- [ ] Page dělá route adaptation (parse param `string → number`, optional search param) a **skládá feature-level containery**, kterým předává route-derived props. To je vše co page dělá.
- [ ] Page neobsahuje business logiku ani podmíněné rozhodování nad daty — to patří do feature containeru.
- [ ] Page nevolá `queryClient.invalidateQueries` přímo.
- [ ] Nová orchestrační logika patří do feature-level container komponenty, ne do page.

## Mutation hooks

- [ ] Hook **nevolá** `navigate()`, `location`, `history`, `window.*` ani nepublikuje žádný toast nebo jiný UI side-effect.
- [ ] Hook se stará o server request, query invalidaci a optimistic update.
- [ ] Page / compose vrstva se stará o navigaci a UX messaging po akci.

## Actor API

- [ ] `useEffectiveActor()` pro UI zobrazení (jméno, oprávnění v UI).
- [ ] `useRealActor()` jen pro audit, billing, security-sensitive logiku.
- [ ] `permissions.ts` a `actorContext.ts` dostávají Actor jako argument — nejsou hookové a **neimportují žádné React hooky**. Jsou to čisté doménové utility.

## Store vs. URL vs. query cache

- [ ] Duplicita server stavu ve store je **chyba** — pokud data přicházejí ze serveru, patří do query cache, ne do store. Výjimka jen s konkrétním zdůvodněním v PR.
- [ ] `currentImageId` ve vieweru **není** ve store — source of truth = route param.
- [ ] Aktivní tab **není** ve store pokud jsou taby route-driven.
- [ ] `viewerStore` drží jen UI stav vieweru (zoom, pan, activeMarkerId, draft coords).

## Cross-feature závislosti

- [ ] Orchestrace mezi features patří do page / compose / layout vrstvy — **ne** přímo do business feature. Feature nesmí řídit jinou feature.
- [ ] Feature **nemanipuluje** (`invalidateQueries`, `setQueryData`) s query keys jiné feature — `cases` nesmí invalidovat cache `photos`, `photos` nesmí sahat do `markers`. Křížová invalidace patří do page / compose vrstvy.
- [ ] `photos` neimportuje z `markers` přímo — coupling je na úrovni `PhotoViewerPage` přes props.
- [ ] `cases` neimportuje interní soubory `photos`, `markers`, `work-items`, `estimates`.
- [ ] Business features (`cases`, `photos`…) nemají přímou závislost na `features/impersonation`.
- [ ] `features/impersonation` konzumují jen `app/` (AppShell, guards, layouts) přes public API.

## Work catalog tree

- [ ] `WORK_TREE` není nikde `.filter()`, `.map()`, `.sort()` ani jinak transformován před předáním do komponenty — strom je vždy předán jako celek.
- [ ] Komponenta přijímá `tree: StaticWorkTree`, ne `WorkTreeArea[]` — branded typ zajišťuje, že transformovaný výsledek nelze předat bez explicitního `as unknown as StaticWorkTree` castu (= viditelné porušení při review).
- [ ] Žádný list se neskrývá podmínkou (`if (!allowed) return null` nebo podobně) — stav se projevuje výhradně jako vizuální overlay:
  - `recommended` → badge / highlight
  - `allowed` → aktivní tlačítko
  - `not allowed` → disabled tlačítko (never hidden)

## Misc

- [ ] Žádný nový interní barrel uvnitř feature bez jasného důvodu.
- [ ] Žádné výjimky v `permissions.ts` závislé na `case.status`, `case.locked` nebo tenant feature flagu — ty patří do `features/cases`.
- [ ] Nová route group má vlastní `errorComponent` + `pendingComponent` — **nesmí spoléhat jen na globální fallback**.
- [ ] Nová mutace je zanesena do matice Query key invalidace v `web-frontend-architecture.md`.
