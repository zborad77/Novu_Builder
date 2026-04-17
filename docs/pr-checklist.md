# PR Review Checklist — Web Frontend

Rychlá kontrola při každém review. Automatika (ESLint + dep-cruiser) chytí hranice importů;
níže jsou věci, které nelze automatizovat.

---

## Importy a vrstvení

- [ ] Všechny importy z jiné feature jdou přes `features/<name>/index.ts` — žádný import z interní cesty (`features/cases/components/CaseCard` je chyba).
- [ ] `*Api.ts` soubory importují jen `apiClient` z `shared/lib/apiClient` — žádný přímý `axios` ani `fetch`.
- [ ] `shared/` nezávisí na `features/`, `pages/`, `app/` ani `store/`.
- [ ] Žádné nové kruhové závislosti (dep-cruiser rule `no-circular`).

## Pages — tenká vrstva

- [ ] Page dělá jen route adaptation (parse param `string → number`, optional search param).
- [ ] Page neobsahuje business logiku ani podmíněné rozhodování nad daty.
- [ ] Page nevolá `queryClient.invalidateQueries` přímo.
- [ ] Nová orchestrační logika patří do feature-level container komponenty, ne do page.

## Mutation hooks

- [ ] Hook **nevolá** `navigate()` ani nepublikuje toast.
- [ ] Hook se stará o server request, query invalidaci a optimistic update.
- [ ] Page / compose vrstva se stará o navigaci a UX messaging po akci.

## Actor API

- [ ] `useEffectiveActor()` pro UI zobrazení (jméno, oprávnění v UI).
- [ ] `useRealActor()` jen pro audit, billing, security-sensitive logiku.
- [ ] `permissions.ts` a `actorContext.ts` dostávají Actor jako argument — nejsou hookové.

## Store vs. URL vs. query cache

- [ ] `currentImageId` ve vieweru **není** ve store — source of truth = route param.
- [ ] Aktivní tab **není** ve store pokud jsou taby route-driven.
- [ ] `viewerStore` drží jen UI stav vieweru (zoom, pan, activeMarkerId, draft coords).
- [ ] Server data (seznam case, markery…) jsou v query cache, ne ve store.

## Cross-feature závislosti

- [ ] `photos` neimportuje z `markers` přímo — coupling je na úrovni `PhotoViewerPage` přes props.
- [ ] `cases` neimportuje interní soubory `photos`, `markers`, `work-items`, `estimates`.
- [ ] Business features (`cases`, `photos`…) nemají přímou závislost na `features/impersonation`.
- [ ] `features/impersonation` konzumují jen `app/` (AppShell, guards, layouts) přes public API.

## Misc

- [ ] Žádný nový interní barrel uvnitř feature bez jasného důvodu.
- [ ] Žádné výjimky v `permissions.ts` závislé na `case.status`, `case.locked` nebo tenant feature flagu — ty patří do `features/cases`.
- [ ] Route group dostala `errorComponent` + `pendingComponent` (viz pravidlo Route-level error + loading boundaries).
- [ ] Nová mutace je zanesena do matice Query key invalidace v `web-frontend-architecture.md`.
