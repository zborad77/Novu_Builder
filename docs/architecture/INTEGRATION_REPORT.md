# Integrační report – F0–F6, modulární refaktor, N9

| | |
|---|---|
| Datum | 2026-10-20 |
| Stav | **Git připraven, validace na aktuálních SHA NOT RUN** (viz §1 Ověření předání) – push až po znovuspuštění kontrol a samostatném potvrzení. Nic nepushnuto, žádný PR, merge ani deployment. |
| Navazuje na | [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md), [PHASE_B_REPORT.md](PHASE_B_REPORT.md), [REFACTOR_FINDINGS.md](REFACTOR_FINDINGS.md) |

## 1. Stav a pořadí PR

PR jsou **řetězené** (každý se zakládá proti předchozí větvi), aby diff každého obsahoval jen jeho část;
po merge předchozího se báze dalšího přepne na `master`. Merge **merge-commitem** (ne squash) –
dokumentace odkazuje na jednotlivé hashe.

| # | Větev → báze | Commity | Rozsah | Obsah |
|---|---|---|---|---|
| PR 1 | `fix/f0-rbac-tenant-isolation` → `master` | 12 vůči `origin/master` (`5b7a278`…`3f581d7`; vůči lokálnímu `master` 10) | 139 souborů | F0 RBAC + tenant izolace, SA-05/06, F0.3, F3 zóny, F3.4/3.6, D-10, F6/F6.2 bare-metal; obsahuje i nepushnutý `5b7a278 docs-cleanup` a merge `904ac05` (dopady: INTEGRATION_PLAN §2) |
| PR 2 | `refactor/modular-architecture` → `fix/f0-rbac-tenant-isolation` | 24 (`5a5eadf`…) | ~720 souborů (převážně přesuny) | B0–B8 modulární monolit, kontrakty, frontend, opravy N10, N2/N2b/N2c, N12, N4, N1, tento report |
| PR 3 | `fix/n9-orm-migration-parity` → `refactor/modular-architecture` | 1 | 13 souborů | N9: ORM = schéma z migrací (bez migrace) |

Postup (každý krok až po potvrzení):
1. `git push -u origin fix/f0-rbac-tenant-isolation` → PR 1 → **plné GitHub CI** (orchestration-release-gate, repo-guard) → review → merge.
2. Teprve po zeleném CI PR 1: push `refactor/modular-architecture`, PR 2 s bází `fix/f0-…` (po merge PR 1 přepnout na `master`) → CI → review → merge.
3. Push `fix/n9-orm-migration-parity`, PR 3 → CI → merge. **N9 je blokér nasazení** – nasazovat až s ním.
4. Lokální `master` po merge srovnat s `origin/master`.

### Ověření předání (NC-001, 2026-10-21)

| Ref | SHA |
|---|---|
| `origin/master` (lokální remote-tracking ref, bez fetch) | `84d9b7365d8c437b3fc3d255e1f5b157ee7c29d4` |
| lokální `master` (+2: `5b7a278`, `904ac05`) | `904ac059ac233ec244caaccb55cd690f067b3e5f` |
| `fix/f0-rbac-tenant-isolation` (PR 1) | `3f581d7f87902daf703356e54e70c38435fde89a` |
| `refactor/modular-architecture` (PR 2) | `027feb654a8b7f69bc5a5de8c09d8d979ea4e1b7` |
| `fix/n9-orm-migration-parity` (PR 3) | `04076a11aba8eb683b42e20eed66b7338b237edf` |

- Řetěz je lineární (každá větev je předkem další); rozsah PR 3 = `git diff refactor/modular-architecture..fix/n9-orm-migration-parity` → 13 souborů.
- Výsledky v §2 jsou historické (2026-10-20). Na výše uvedených SHA je 2026-10-21 **nikdo znovu nespustil**:
  pytest, `export_contracts --check`, `lint-imports`, ruff, alembic, CI joby ani buildy jsou **NOT RUN**.
  Pokus 2026-10-21 (`src/backend/.venv/Scripts/python.exe -m scripts.export_contracts --check`,
  `npm --prefix src/frontend run build`) runtime NovuAI odmítl, protože spouštění programů vyžaduje ruční
  schválení a neinteraktivní běh ho nemá. Oficiální build skripty **existují**: `src/frontend/package.json`
  (`build`, `typecheck`, `lint`) a `src/desktop/scripts/build-debug.ps1`; v kořeni repa žádný
  `build.bat|cmd|sh` není. Před push je nutné kontroly i buildy spustit znovu na těchto SHA.
- Otevřené k rozhodnutí: starý `stash@{0}` („my-feature-changes“, staré rozložení adresářů), nesloučená
  `origin/fix/v086-rehearsal-followup-2-sse-publish` (lokálně ji nahrazuje N12 `0302694`) a jednorázový
  skript `src/backend/tools/refactor/n9_add_server_defaults.py` v PR 3.

### NC-001B – znovuověření (2026-10-21)

- Git (ověřeno): `origin/master` je předkem `fix/f0-…`; `fix/f0-…` předkem `refactor/…`; `refactor/…`
  předkem `fix/n9-…`. Rozsahy: PR 1 12 commitů / 139 souborů (`origin/master..fix/f0-…`), PR 2 24 commitů /
  722 souborů, PR 3 1 commit (`04076a1`) / 13 souborů. Očekávané commity refaktoru (B0–B8, N10 `5a5eadf`
  + `1aee30b`, N2 `c1d23cd`, N12 `0302694`, N2b `24f58b5`, N4 `6fe92bc`, N1 `15f8e2f`, N2c `4104bad`,
  report `027feb6`) i N9 `04076a1` jsou přítomny.
- Duplicity: `INTEGRATION_PLAN.md` a `INTEGRATION_REPORT.md` existují jen v `docs/architecture/`;
  `.novu/` obsahuje jen `memory/architecture_principles.json` (metadata NovuAI, necommitovat).
- **BLOCKED:** aktuální stav na GitHubu (`git ls-remote`/`fetch`) a všechny validace (`export_contracts
  --check` zkoušen znovu) – runtime vyžaduje ruční schválení spuštění. Závislé kroky (push, PR, CI)
  **NOT RUN — DEPENDS ON** ručním spuštění validací na SHA výše.
- Necommitované úpravy těchto dvou dokumentů leží na `fix/n9-…`; po schválení je commitnout tamtéž
  (docs commit v PR 3), aby se nemusel přepisovat řetěz PR 1–2.

#### Vypořádání Review NC-001B (kolo 1, verdikt `changes`)

##### Registr připomínek Review (autoritativní seznam, kolo 8, 2026-10-21)

**Zdroj:** záznamy orchestrace NovuAI předané agentovi v kontextu úlohy „Fix R2“: záznamy úloh
Workflow #8–#12 (kroky Review a User Acceptance) a otevřené úlohy z nálezů Multi-Agent runu #10
(„Fix R1“, „Fix R2“, „Fix F4“, „Unblock: …“). V repu žádné záznamy Review nejsou: `.novu/` obsahuje jen
`memory/architecture_principles.json` a prázdné `validation-logs/`. Fulltext v `docs/**` (kolo 3)
našel shodu jen v těchto dvou dokumentech. Registr proto vychází z těchto záznamů orchestrace a
každý řádek na svůj záznam odkazuje.

**Pravidlo úplnosti (nahrazuje dřívější „jinak je závěrečné review potvrdí jako úplné“):**
1. Úplnost se **nikdy** nepotvrzuje tím, že chybí další záznamy. Nenalezený záznam není důkaz,
   že žádná připomínka neexistuje.
2. Každé Review s verdiktem `changes` (Workflow #8, #9, #10/run #10, #11, #12) musí mít v registru
   všechny své připomínky s doslovným zněním a odkazem na zdroj.
3. Řádek je **UZAVŘENO** jen s ověřitelným důkazem: SHA, cesta k souboru nebo logu, příkaz
   a jeho exit kód. Stavy BLOCKED, OTEVŘENO a NEDOLOŽENO uzavření R2 blokují.
4. U Review, jehož znění orchestrace nepředala (řádek W8; W9 je od kola 15 doložený nálezy F1–F3),
   zůstává stav **NEDOLOŽENO**.
   Platí to, dokud uživatel nebo orchestrace nedodá doslovné znění. Agent ani závěrečné
   review tento stav nesmí změnit bez dodaného znění.

| ID | Zdroj | Znění připomínky (dle orchestrace) | Stav | Důkaz / co chybí |
|---|---|---|---|---|
| W8 | Workflow #8 (Development Roadmap), Review, verdikt `changes`; Coding kolo 2 „opravil tři nálezy“ | **znění nepředáno** (záznam uvádí jen počet: 3) | **NEDOLOŽENO** | chybí doslovné znění 3 nálezů. Změny Coding kola 2 jsou jen v necommitovaném diffu `docs/architecture/INTEGRATION_*.md` vůči `027feb6`, ale jejich přiřazení k nálezům nejde ověřit |
| W9 / F1(#9) | Multi-Agent run #9 (Workflow #9, NC-001B), Review `partial`, verdikt `changes`; úloha „Fix F1: R1: Chybí aktuální…“ | „R1: Chybí aktuální úspěšné buildy a testy požadované akceptací.“ (doslovně z úlohy, kolo 13) | **BLOCKED (= R1)** | věcně shodné s R1 a vede se pod ním. Kolo 13: spuštění `build.bat` runtime znovu odmítl („requires approval“). Run #9 předal i F2 a F3 (řádky níže) |
| W9 / F2(#9) | Multi-Agent run #9 (Workflow #9, NC-001B), Review; úloha „Fix F2: R3: Spuštěný git ls-remote…“ | „R3: Spuštěný git ls-remote selhal připojením ke github.com:443; vzdálený stav není ověřený.“ (doslovně z úlohy, kolo 14) | **BLOCKED (= R3)** | věcně shodné s R3 a vede se pod ním. Kolo 14: `git ls-remote origin …` runtime znovu odmítl („requires approval“), síťový dotaz neproběhl. Uzavře ho stejný důkaz jako R3 |
| W9 / F3(#9) | Multi-Agent run #9 (Workflow #9, NC-001B), Review; úloha „Fix F3: R2: Nepodložené tvrzení…“ | „R2: Nepodložené tvrzení o neexistenci záznamů bylo opraveno, ale úplnost a vypořádání původních připomínek zůstávají doloženy jen částečně.“ (doslovně z úlohy, kolo 15) | **OTEVŘENO (= R2)** | věcně shodné s R2 a vede se pod ním. 1. část nálezu (nepodložené tvrzení) je opravená pravidlem úplnosti bod 1. Úplnost zůstává částečná kvůli W8 (2 ze 3 nálezů bez znění) a F4 (zkrácené znění); vypořádání kvůli BLOCKED řádkům R1/R3. Uzavře ho totéž co R2 (podmínky pod tabulkou) |
| R1 | Multi-Agent run #10 (Workflow #10), Review; úloha „Fix R1“ | „Aktuální buildy a testy stále nejsou doložené. Kolo 6 uvádí neprovedené příkazy a připravený skript bez výsledného logu.“ | **BLOCKED** | `.novu/validation-logs/` je prázdné, žádný log ani exit kód neexistuje. Kolo 8: spuštění `src/backend/.venv/Scripts/python.exe --version` runtime znovu odmítl („requires approval“). Uzavře ho log příkazů níže na `04076a1` |
| R2 | Multi-Agent run #10, Review; úloha „Fix R2“ | „Úplnost původních připomínek a jejich vypořádání nejsou doložené. Tabulka stále připouští potvrzení úplnosti závěrečným review bez dodání podkladů.“ | **OTEVŘENO** | 2. část (potvrzení nepřítomností) je odstraněná pravidlem úplnosti výše. 1. část blokuje řádek W8 (NEDOLOŽENO) a zkrácené znění F4. W9 je od kola 15 doložený (F1–F3 z runu #9) |
| R3 | Multi-Agent run #10, Review; úloha „Fix R3“ | „Vzdálené reference zůstávají neověřené. Aktuální git ls-remote skončil kódem 1 kvůli nedostupnosti github.com:443.“ | **BLOCKED** | kola 2–7 a kolo 9: runtime vyžadoval ruční schválení (`git ls-remote origin`, `git fetch origin --dry-run`), síťový dotaz neproběhl. Lokální cache viz „Kolo 9“ níže – **není** důkazem aktuálního stavu. Uzavře ho výstup `git ls-remote origin refs/heads/master refs/heads/fix/f0-rbac-tenant-isolation refs/heads/refactor/modular-architecture refs/heads/fix/n9-orm-migration-parity` s exit kódem 0, porovnaný s §1 |
| B1 | blokace Multi-Agent runu #10; úloha „Unblock: not run - the project defines no build Dev Command“ | „not run - the project defines no build Dev Command“ | **ČÁSTEČNĚ** | v kořeni existuje `build.bat` (3029 B, necommitovaný, viz `BUILD_SCRIPT_NOTES.md`). Skript zatím nikdo nespustil, splnění kritéria „blokovaný krok lze spustit“ tedy doložené není |
| B2 | blokace Multi-Agent runu #10; Workflow #11 | „Permission: Claude CLI can edit files here but runs no commands without Full Access“ | **ČÁSTEČNĚ** | kolo 8: `git rev-parse HEAD` (→ `04076a1…`), `git status` a `git diff` proběhly. Spuštění `.venv` Pythonu dál vyžaduje ruční schválení |
| F4 | úloha „Fix F4“ (Review blokace; zdrojový run v předaném záznamu neuveden) | „Odstranění blokace nebylo doloženo. Podle předání validační příkazy s…“ (orchestrace znění zkrátila) | **OTEVŘENO** | závisí na B1, B2 a R1. Chybí i plné znění |
| W11/W12 | Workflow #11 a #12, Review, verdikt `changes` | dle stavu kroků: build a testy nebyly doložené | **= R1, F4** | nejde o nové připomínky. Vedou se pod R1 (Workflow #12 = úloha „Fix R1“) a F4 |
| F1 | Multi-Agent run #8 (Workflow #8, Development Roadmap), Review; úloha „Fix F1“ | „Doložit výsledky požadovaných buildů, testů a kontrol OpenAPI, migrací a modulárních hranic pro předávaný stav; report je stále označuje NOT RUN.“ | **BLOCKED** | věcně shodné s R1 (navíc výslovně OpenAPI, migrace, modulární hranice). Kolo 11: `build.bat`, `& build.bat` i `.venv\Scripts\python.exe --version` runtime odmítl („requires approval“), takže nic neproběhlo. Uzavře ho log z ruční validace níže na `04076a1` s exit kódy kroků `build.bat`, `pytest`, `export_contracts --check` (OpenAPI/routy), `alembic upgrade head` + `alembic check` (migrace) a `lint-imports` (hranice). Je to 1 ze 3 nálezů W8 – znění zbylých dvou stále chybí |

R2 se uzavře, až budou splněné obě podmínky:
1. Uživatel nebo orchestrace dodá doslovné znění zbylých 2 nálezů W8 (F1 z runu #8 už je zapsaný)
   a plné znění F4. Agent je zapíše jako samostatné řádky a doplní k nim důkaz.
2. Všechny řádky mají stav UZAVŘENO nebo jsou výslovně odkázané na jiný řádek se stavem UZAVŘENO.

Kolo 4 (2026-10-21, lokální git bez sítě): předkovství `origin/master` ⊂ `fix/f0-…` ⊂ `refactor/…` ⊂ `fix/n9-…`
a rozsahy PR 1 12/139, PR 2 24/722, PR 3 1/13 znovu potvrzeny; SHA v §1 beze změny; `stash@{0}` stále existuje.

Kolo 5 (2026-10-21): lokální SHA beze změny (`fix/f0-…` `3f581d7`, `refactor/…` `027feb6`, `fix/n9-…` = HEAD
`04076a1`, `origin/master` `84d9b73`). Runtime znovu vyžadoval ruční schválení pro `git ls-remote origin`,
`python -m pytest tests/` i `python -m ruff check app/`, takže nic z toho neproběhlo. `.novu/` obsahuje jen
`memory/architecture_principles.json` a žádné záznamy Review. Build skript v kořeni repa není (`build.bat`
je jen v `src/desktop/`). R1–R3 se agentem uzavřít nedají. Zbývá ruční validace uživatelem nebo schválení
příkazů v runtime a pro R2 dodání seznamu připomínek z orchestrace.

Kolo 6 (2026-10-21): runtime znovu vyžadoval ruční schválení pro `git ls-remote origin …` a pro
`src/backend/.venv/Scripts/python.exe -m ruff check app/`, takže nic z toho neproběhlo. Příkazy níže
jsou připravené jako jeden validační skript (mimo repo, v pracovním adresáři agenta). Skript zapisuje
výstup a `EXIT[krok]` každého kroku do logu. Další kolo vyhodnotí R1 a R3 přímo z tohoto logu.

Kolo 7 (2026-10-21, HEAD `04076a1`, `.claude/settings.local.json` stále jen `Bash(xargs ls *)`): projde jen
`python --version` (dotaz na verzi, 3.13.14). Ruční schválení dál vyžadují `python -m ruff --version`,
`python -m pytest tests/architecture -q`, `npm --version` i `.venv\Scripts\python.exe -m ruff check app/`.
Runtime profil NovuAI (`E:\NovuHub_Database\…\runtime_profiles\claude-cli`) leží mimo workspace a agent ho
nesmí číst. Příčinou je tedy pořád chybějící oprávnění ke spouštění. Odstranit ji může jen uživatel:
buď spustí krok s „Full Access“, nebo výslovně schválí úzký allowlist do `.claude/settings.local.json`.
Agent si vlastní oprávnění nerozšiřuje.

Kolo 9 (2026-10-21, úloha „Fix R3“, HEAD `04076a1`): `git ls-remote origin` i `git fetch origin --dry-run`
runtime znovu odmítl („requires approval“), dotaz na `https://github.com/zborad77/Novu_Builder.git` tedy
neproběhl a exit kód neexistuje. Lokálně (`git for-each-ref refs/remotes/origin`, reflog) šlo zjistit jen
stav z **posledního fetch 2026-10-17 09:09** (`pull --ff-only`):

| Ref | lokální SHA | `origin/*` v cache (2026-10-17) | Aktuální remote |
|---|---|---|---|
| `master` | `904ac05` (+2) | `84d9b73` | NEOVĚŘENO |
| `fix/f0-rbac-tenant-isolation` | `3f581d7` | ref neexistuje | NEOVĚŘENO |
| `refactor/modular-architecture` | `027feb6` | ref neexistuje | NEOVĚŘENO |
| `fix/n9-orm-migration-parity` | `04076a1` | ref neexistuje | NEOVĚŘENO |

Dopad na plán (§1 Postup): beze změny, ale platí jen za předpokladu, že se remote od 2026-10-17
nezměnil. Po úspěšném `ls-remote` se rozhoduje takto:
- `master` = `84d9b73` a žádná ze tří větví na remote → postup §1 platí beze změny (první push `-u`).
- `master` ≠ `84d9b73` → přepočítat rozsah PR 1 (`git fetch` + `origin/master..fix/f0-…`), zvážit rebase F0
  (až po schválení) a znovu spustit validace R1.
- Některá ze tří větví na remote existuje → porovnat SHA s tabulkou. Při shodě push odpadá, při
  rozdílu nic nepřepisovat (žádný force push) a rozhodnout ručně.

Kolo 11 (2026-10-21, úloha „Fix F1“, HEAD `04076a1`): `git rev-parse` a `git status` proběhly. Spuštění
`build.bat` (přes `cmd.exe` i PowerShell) a `src/backend/.venv/Scripts/python.exe --version` runtime znovu
odmítl („requires approval“). Build, testy, `export_contracts --check`, alembic ani `lint-imports` tedy
neproběhly a `.novu/validation-logs/` zůstává bez logu. F1 i R1 zůstávají **BLOCKED** a stav v hlavičce
reportu („NOT RUN“) je dál pravdivý.

Kolo 12 (2026-10-21, úloha „Implement … Development Roadmap“, D1 `source_change` z runu #8, HEAD `04076a1`):
rozsah Workflow #8 (NC-001) je ověření předání, pořadí PR a aktualizace `INTEGRATION_*.md`. Žádný jeho úkol ani
nález (F1, W8) nepožaduje změnu kódu a report neuvádí chybu v kódu k opravě. Kód se proto **záměrně neměnil**:
nevynucená změna by posunula ověřené SHA řetězu PR 1–3. D1 je u NC-001 stejně jako u NC-001B chybně přiřazené
kritérium a je potřeba ho v orchestraci zrušit. Build se nespouštěl, protože se neměnil kód.

Kolo 13 (2026-10-21, úloha „Fix F1“ z runu #9, HEAD `04076a1`): `git rev-parse` a `git status` proběhly, v kořeni
je jen `build.bat` (`build.cmd`/`build.sh` nejsou). Jediný pokus o spuštění
`cmd.exe /c build.bat > .novu\validation-logs\build-04076a1.log 2>&1` runtime odmítl („requires approval“), build
neproběhl a log nevznikl. Znění F1 z runu #9 je zapsané do řádku W9 registru. F1 (#9) zůstává **BLOCKED** spolu s R1.

Kolo 14 (2026-10-21, úloha „Fix F2“ z runu #9, HEAD `04076a1`): jediný pokus o
`git ls-remote origin refs/heads/master refs/heads/fix/f0-rbac-tenant-isolation refs/heads/refactor/modular-architecture refs/heads/fix/n9-orm-migration-parity`
runtime odmítl („requires approval“), dotaz na GitHub neproběhl a exit kód neexistuje. Znění F2 z runu #9 je zapsané
do registru (řádek W9 / F2). Tabulka „Kolo 9“ i plán §1 zůstávají beze změny. F2 (#9) zůstává **BLOCKED** spolu s R3.

Kolo 15 (2026-10-21, úloha „Fix F3“ z runu #9, HEAD `04076a1`): znění F3 z runu #9 je zapsané do registru (řádek
W9 / F3). Run #9 tím má doložené nálezy F1, F2 a F3, které odpovídají jeho R1, R2 a R3, a řádek W9 už není
NEDOLOŽENO. Úplnost runu #9 se tím **nepotvrzuje** nepřítomností dalších nálezů (pravidlo úplnosti bod 1), jen
se zapisuje, co orchestrace předala. F3 zůstává **OTEVŘENO** spolu s R2: chybí znění 2 nálezů W8 a plné znění F4
a vypořádání blokují R1 a R3. Kód se neměnil, build ani testy se nespouštěly.

Dokud R1 a R3 nejsou splněné, NC-001B **není přijatý** a push, PR i CI zůstávají **NOT RUN — DEPENDS ON** R1 a R3.

Ruční validace (z `src/backend/`, venv `.venv`), zaznamenat exit kódy a SHA:

```powershell
git -C ../.. rev-parse HEAD                      # očekáváno 04076a1…
.venv\Scripts\python.exe -m ruff check app/
.venv\Scripts\python.exe -m mypy app/
.venv\Scripts\python.exe -m bandit -r app/ -ll -ii
.venv\Scripts\lint-imports.exe
.venv\Scripts\python.exe -m scripts.export_contracts --check
.venv\Scripts\alembic.exe upgrade head; .venv\Scripts\alembic.exe check   # migrace = ORM (F1)
..\..\build.bat                                  # projektový build skript (F1, B1)
.venv\Scripts\python.exe -m pytest tests/ -q --cov=app --cov-fail-under=40
npm --prefix ..\frontend run typecheck; npm --prefix ..\frontend run lint; npm --prefix ..\frontend run build
powershell -ExecutionPolicy Bypass -File ..\desktop\scripts\build-debug.ps1
git fetch origin; git rev-parse origin/master    # porovnat s 84d9b73 v §1
```

Pokud se `origin/master` po fetch posune, je nutné znovu přepočítat rozsahy PR 1 a zvážit rebase F0 (až po schválení).

### Pravidla pro navazující práci (NC-002 až NC-004)

- Výchozí větev: `fix/n9-orm-migration-parity` na commitu s těmito dokumenty (dnes `04076a1` + docs
  commit); po merge PR 1–3 výhradně `master`. Nezakládat z lokálního `master` (chybí refaktor i N9).
- Každý úkol ve vlastní větvi `feature/nc-00X-…` a vlastním worktree uvnitř workspace.
- Společné soubory mění vždy jen jeden úkol a předává je sériově: `src/contracts/`,
  `src/backend/tests/architecture/baseline/`, `src/backend/app/composition/router.py` a `wiring.py`,
  `src/backend/alembic/versions/` (jedna nová revize najednou), `src/backend/pyproject.toml`, `.github/workflows/`,
  `docs/architecture/INTEGRATION_*.md`.

## 2. Výsledky CI

**GitHub CI na těchto commitech zatím neběželo** (vyžaduje push). Lokální ekvivalent všech jobů
`orchestration-release-gate` (Windows 11, Python 3.13, Node 24, PostgreSQL 16 + Redis 7):

| Job | PR 1 (`3f581d7`) | PR 2 (`refactor/…`) | PR 3 (`fix/n9-…`) |
|---|---|---|---|
| lint: ruff / mypy / bandit / pip-audit | ✔ / 0 chyb / 0 / – | ✔ / 0 / 0 / bez zranitelností | ✔ / 0 / 0 / – |
| lint: lint-imports, desktop↔API kontrakt | – | ✔ KEPT, ✔ 36 cest | ✔ |
| web-lint: typecheck, eslint, dep-cruise (+ check:contracts, build) | ✔ (build ✘ → N10) | ✔ vše | beze změny webu |
| test: pytest PG + Redis | 1786 passed, 1 skipped | 1811 passed, 1 skipped (+ N2c: cílené testy) | **1819 passed, 1 skipped** |
| test: živé sondy (verify_deploy, kontrakty, auth, business flow) | – | ✔ všech 5 | – |
| postgresql-migrations | 17/17 | 19/19 | 19/19 (nulový rozdíl ORM × migrace) |
| deployment-config (compose + MinIO ze zdrojů) | nespuštěno | `docker compose config` ✔, image ✔ | – |
| deploy-linux-config | ✔ | ✔ ALL CHECKS PASSED | – |
| desktop build (mimo CI) | – | ✔ MSVC + Qt 6.10.3 | – |

Audit účinnosti mocků: 579/579 volaných mocků zachováno na všech větvích.

## 3. Kontrola před push (provedena)

| Kontrola | Výsledek |
|---|---|
| repo-guard (zakázané soubory, PEM) na všech třech větvích | čisté |
| `scripts/ci-check-no-secrets.sh` | hlásí `src/backend/.env.production.example` – planý poplach na `CHANGE_ME_*` placeholderech v URL, **stejně už na `origin/master`**; skript není v CI |
| Hledání secrets v přidaných řádcích (`origin/master..fix/n9-…`, 95 tis. řádků) | jen testovací hesla ve fixtures bezpečnostních testů |
| Lokální cesty / jména stroje v commitech | žádné |
| Autor commitů | jednotně `Novusion <pavel.dostal@novusion.cz>`; atribuce v každém commitu refaktoru |
| Binární soubory | jen `design/NovuBuilder.png` (z `docs-cleanup`) |
| Velké generované soubory | kontrakty a baseline (openapi.json 15 tis. ř., mock_audit.json 19 tis. ř., generated openapi.ts 8 tis. ř.) – záměrné |

## 4. Změny chování

**PR 1 (F0–F6)** – bezpečnostní změny dle CHANGELOG (superadmin jen v zóně admin, RBAC role, tenant
izolace, soft delete/purge fotek, zónové JWT, gateway HMAC, device binding, D-10). Migrace 0057–0059.
`docs-cleanup`: SQL echo natvrdo vypnutý, potlačené hlučné loggery (otázka I1).

**PR 2 (refaktor + opravy)**
| Změna | Dopad |
|---|---|
| Cesty `src/backend`, `src/frontend`, `src/desktop` | bare-metal: nový venv v `/opt/novuconstruct/src/backend/.venv`; compose build kontext |
| Rate limity klíčované modulem routy | jednorázový reset čítačů při nasazení (O8 – schváleno) |
| Jména loggerů = nové cesty modulů | dotazy/alerty filtrující podle loggeru (`app.core.…`) upravit; alerting podle textu událostí beze změny |
| `init_modules()` ve všech vstupních bodech | chybějící propojení = okamžitá výjimka (dřív tiché vynechání) |
| N12 `publish` | **živé SSE události začnou fungovat** (dosud jen replay outboxu) – ověřit klienty |
| N2/N2c offer worker | nová služba, **nezapíná se automaticky**; `AI_OFFER_PROVIDER=mock` výchozí; `claude` jen s platným klíčem a tvrdými rozpočty |
| N2b budget sweeper | prošlé rezervace AI budgetu se začnou uvolňovat |
| N4 desktop admin | admin panel desktopu volá správné URL (funguje jen proti zóně admin) |
| Web | labely akcí ze serveru (shodné texty), `npm run build` funkční (N10) |
| API, DB schéma, migrace, middlewary, zóny, RBAC | **beze změny** (zmrazené baseline) |

**PR 3 (N9)** – jen ORM: testy a dev (`create_all`) dostanou indexy, server defaulty a tabulku
`reconciler_events` jako produkce. Produkční schéma ani data se nemění.

## 5. Zbývající blokery nasazení

| # | Blokér | Stav / co je potřeba |
|---|---|---|
| B-1 | GitHub CI na PR 1–3 | po potvrzení push |
| B-2 | **N9** | opraveno ve PR 3 – nasazovat až s ním |
| B-3 | **S-1 objektové úložiště** (F6.2) | `nc-provision start` bez `NC_OBJECT_STORAGE_READY=1` API nespustí – rozhodnutí v OBJECT_STORAGE_OPTIONS.md |
| B-4 | Staging ověření (§6) | nespuštěno |
| B-5 | Gateway (F4) | core strana (HMAC, allowlist, zóna gateway) hotová; samotný gateway proces (F4.1–4.8) dle IMPLEMENTATION_PLAN otevřen – zóna gateway na stagingu jen s testovacím podepisovačem |
| B-6 | Offer worker | zapnout až po `nc-provision offer-worker` (backlog) a rozhodnutí o `claude` |
| B-7 | Otevřené fáze plánu bezpečnosti | F5 (MFA), F6.3–F6.7, F7 – potvrdit, které jsou podmínkou pilotu |

## 6. Plán stagingu

Prostředí: čistý Ubuntu 24.04 (Hetzner) + kopie produkční DB (anonymizovaná dle pravidel provozovatele).

| # | Krok | Ověření |
|---|---|---|
| S1 | Čistá instalace: rozbalit release do `/opt/novuconstruct`, `nc-provision preflight`, `plan`, `install` | preflight bez blokací; `install` idempotentní (2. běh = 0 změn) |
| S2 | Migrace čisté DB: `nc-provision migrate` | head `20261017_0059`; `nc-migrate status` up to date |
| S3 | Migrace existující DB: obnovit kopii produkce (0055/0056) → `nc-provision migrate` | pg_dump záloha vznikla; head 0059; RBAC opravy dle migrace 0057; `alembic check` bez rozdílu (N9) |
| S4 | `nc-provision start` + `smoke` | nc-api@desktop/admin, nc-worker aktivní; porty jen loopback/socket; Redis ACL; práva DB (audit_logs append-only) |
| S5 | Workery | analýza (mock) projde fronta → výsledek; heavy lane export; `ready/processing?strict=1` = ready |
| S6 | Offer worker | `nc-offer-backlog` → posoudit; `NC_CONFIRM_OFFER_BACKLOG=1 nc-provision offer-worker` s `mock`; poté (volitelně) `claude` s testovacím klíčem a tvrdým rozpočtem |
| S7 | SSE | desktop/web dostanou živé `analysis.started`, `proposal.ready` (N12) i replay po reconnectu bez duplicit |
| S8 | Gateway | zóna gateway: nepodepsaný požadavek 401, podepsaný (test vector) 2xx, routa mimo allowlist 404, X-Forwarded-For ignorován |
| S9 | WG zóny | `deploy/linux/tests/network_isolation.sh` scénáře N1–N12; desktop přes wg-nc, admin přes wg-nc-admin; superadmin mimo admin zónu odmítnut |
| S10 | Přístupová oprávnění | bezpečnostní scénáře F0/D-10: tenant A nevidí data B; firemní admin jen vlastní firmu; purge fotky s auditem a ledgerem |
| S11 | Záloha a obnova | `scripts/backup.sh` → `ops/restore.sh` na čistý stroj; `verify_restore.sh`; kontrola konzistence úložiště |
| S12 | Rate limity | po nasazení čítače od nuly (O8); 429 po překročení limitu loginu |

## 7. Rollback

| Situace | Postup |
|---|---|
| Před merge | zavřít PR; nic se nenasadilo |
| Po merge, před nasazením | revert merge commitu PR (merge-commit → `git revert -m 1`) |
| Nasazení selže před migrací | ponechat předchozí release v `/opt/novuconstruct` (doporučeno: release do vedlejšího adresáře a přepnutí symlinkem), `systemctl restart nc-core.target` |
| Nasazení selže po migraci 0057–0059 | DB vrátit z pg_dump, který `nc-migrate` udělal před upgrade (`/var/backups/novuconstruct`); downgrade 0059 odmítne běžet při fotkách ve stavu `purge_pending` – proto obnova ze zálohy, ne downgrade |
| Problém jen s offer workerem | `systemctl disable --now nc-offer-worker` (ostatní služby nedotčeny) |
| Problém se živým SSE (N12) | klienti mají fallback na replay outboxu; revert jediného commitu `0302694` |
| Refaktor (cesty) | starý release s `python-backend/` + jeho venv; jednotky systemd z téhož release (`.nc-bak` zálohy) + `daemon-reload` |

Před produkcí: tag `pre-f0-merge` na `origin/master`, záloha DB a konfigurace `/etc/novuconstruct`.

## 8. Úklid lokálního prostředí

| Položka | Stav |
|---|---|
| Kontejnery `nc-refactor-pg`, `nc-refactor-redis` (+ anonymní volumes), image `nc-refactor-backend:b8` | odstraněny |
| `novutrade-backend` a ostatní projekty | **nedotčeny** (Docker Desktop běží; byl spuštěn během refaktoru, NovuTrade kontejner se rozběhl vlastní restart policy) |
| `J:/tmp/nc_webtest` | **nesmazáno** (ochrana nástroje proti mazání mimo repozitář) – nejdřív `rmdir J:\tmp\nc_webtest\node_modules` (junction), pak složku |
| Pomocný worktree a scratch soubory | odstraněny / mimo repozitář |

### 8.1 Úklid pracovní kopie (TK-00041, 2026-11-06)

Výchozí stav: větev `feat/nc-007-secure-web-platform`, HEAD `ea5d5f9`, index prázdný,
`stash@{0}: On master: my-feature-changes` (ponechán, bez `pop`/`drop`/`clear`).
Nic se nemazalo; nepoužit `reset --hard`, `clean`, `restore`.

| Položka | Rozhodnutí | Důvod / ověření |
|---|---|---|
| `.gitignore` | **mimo rozsah tohoto běhu – necommitnuté, commit čeká na schválení** | Přidáno `.coverage`, `.coverage.*`; dřívější řádek `.novu/` (metadata NovuAI) ponechán. Ověřeno: `src/backend/.coverage` není v `git status --porcelain` (soubor zůstal na disku). Určeno ke commitu `[TK-00041]` spolu s `.gitattributes`; `git add -- .gitignore .gitattributes` v tomto běhu čeká na schválení. |
| `.gitattributes` | **mimo rozsah tohoto běhu – necommitnuté, commit čeká na schválení** | `*.bat`/`*.cmd` `eol=crlf`. Ověřeno: `build.bat` i `test.bat` už mají CRLF (`file`). Commit viz řádek `.gitignore`. |
| `src/backend/.coverage` | ignorováno | lokální artefakt pytest-cov, nesmazán |
| `build.bat`, `test.bat` | **mimo rozsah – ponecháno necommitnuté** | Skripty jsou staticky v pořádku (CRLF, návratové kódy 0/1/2), ale ani jednou neběžely: `cmd.exe /c build.bat` i `cmd.exe /c test.bat pytest …` v tomto běhu čekají na schválení. Commit až po skutečném běhu. |
| `docs/architecture/BUILD_SCRIPT_NOTES.md` | mimo rozsah – necommitnuté | patří k `build.bat`/`test.bat`, commituje se s nimi; doplněn stav TK-00041 |
| `src/backend/tests/test_case_transition_effects.py` (N11, fixture `test_tenants`) | **mimo rozsah – necommitnuté, runtime NEOVĚŘENO** | Ověření patří do T3 (N11) na izolované PostgreSQL DB; pytest v tomto běhu čeká na schválení. |
| `INTEGRATION_PLAN.md`, `PHASE_B_REPORT.md`, `REFACTOR_FINDINGS.md`, `INTEGRATION_REPORT.md` | mimo rozsah – necommitnuté | Rozpracovaná dokumentace dřívějších běhů (NC-001, N11); obsah se nepřepisoval, jen doplněn tento oddíl. Commitovat spolu s výsledky validace, kterých se týká. |

Build: **nespuštěno** (`build.bat` čeká na schválení). Testy: **nespuštěny** (`test.bat` čeká na schválení).

**Kolo 2 (Review F1, F2), 2026-11-06.** Znovu ověřeno: HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
větev `feat/nc-007-secure-web-platform`, `stash@{0}` = `614a92a34453c03fae6e27f7370e49a32510e733`
(beze změny), `git status --porcelain` = 7× `M` a 3× `??` uvedené výše, `.coverage` v něm není.
Pokusy v tomto běhu – všechny **nespuštěny, čekají na schválení** (nejde o selhání):
`cmd.exe /c build.bat`, `git add -- .gitignore .gitattributes`, `git check-ignore -v src/backend/.coverage`.
Zbylé položky pracovní kopie jsou tedy výslovně mimo rozsah tohoto běhu podle tabulky.
Po schválení: (1) `git add -- .gitignore .gitattributes` a commit `[TK-00041]`, (2) jednou `build.bat`,
(3) `test.bat backend`; N11 zůstává v T3, dokud nemá vlastní runtime ověření.

**Kolo 3 (run #98, 2026-11-07).** Znovu ověřeno: HEAD `ea5d5f9d2164f671989fd4dfb87d818b219cce84`,
větev `feat/nc-007-secure-web-platform`, `stash@{0}` = `614a92a34453c03fae6e27f7370e49a32510e733`
(beze změny, bez `pop`/`drop`). `git status --porcelain` = **9× `M` a 3× `??`** – oproti kolu 2 přibyly
`AGENTS.md` a `CLAUDE.md`. `git check-ignore -v`: `src/backend/.coverage` → `.gitignore:31:.coverage`,
`.coverage.*` → řádek 32, `.novu/` → řádek 110; `git ls-files src/backend/.coverage` je prázdné (soubor
není sledovaný, zůstal na disku). `build.bat` i `test.bat` mají CRLF (`file`). Předpoklady buildu
existují (`src/backend/.venv/Scripts/python.exe`, `lint-imports.exe`, `src/frontend/node_modules`).

| Položka | Rozhodnutí | Důvod |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md` | **mimo rozsah – cizí rozpracovaná práce, necommitnuté** | Vložené bloky `novusion-development-hygiene` a `novusion-authorship-standard` (správa pravidel workspace, ne TK-00041). Obsah se neměnil. |
| ostatní položky | beze změny podle tabulky výše | – |

Build: **nespuštěno – čeká na schválení** (`cmd.exe //c build.bat` runtime vrátil „requires approval“;
nejde o selhání). Testy: **nespuštěny** – `test.bat` je stejná třída příkazu a bez běhu buildu se
nespouštěl. Blokace kroku build tedy trvá; jejím odstraněním je jen schválení spuštění `build.bat`
uživatelem, technická překážka v repozitáři (chybějící skript, LF konce řádků, chybějící `.venv`/
`node_modules`) nebyla nalezena. Dočasné výstupy buildu (TEMP/TMP) mají jít do `build/tmp` uvnitř
repozitáře; `build/` zatím neexistuje.

## Příloha A – texty PR (k potvrzení)

### PR 1 – Security hardening F0–F6
> **Base:** `master` ← `fix/f0-rbac-tenant-isolation`
>
> Bezpečnostní fáze F0–F6 podle `docs/security/IMPLEMENTATION_PLAN.md`: RBAC a tenant izolace (SA-01..SA-04), trusted client IP (SA-05), tenant RBAC + soft delete fotek (SA-06), vlastnictví a trvalé mazání fotek s ledgerem (F0.3), síťové zóny + exposure guard + zónové JWT (F3), podpis gateway (F3.4), device binding (F3.6), firemní správa uživatelů (D-10), bare-metal Private Core/Public Edge a idempotentní provisioning (F6, F6.2).
> Migrace 0057–0059 (nevratný downgrade 0059 při `purge_pending`). Obsahuje i dříve nepushnutý `docs-cleanup` (dokumenty obnoveny v `dcf210f`).
> Lokálně: pytest 1786 passed, migration_tests 17/17, deploy-linux ✔. Detail: `docs/architecture/INTEGRATION_PLAN.md`.

### PR 2 – Modulární monolit (src/backend, src/frontend, src/desktop, src/contracts)
> **Base:** `fix/f0-rbac-tenant-isolation` (po merge PR 1 → `master`)
>
> Modulární refaktor (Fáze B, `docs/architecture/MODULAR_ARCHITECTURE.md`): repozitář v `src/`, backend jako modulární monolit (11 modulů s `public.py`, `platform`, `composition`), hranice vynucené import-linterem a `tests/architecture`, sdílené kontrakty v `src/contracts`, frontend bez duplicitní business logiky. **API, DB schéma, migrace, pořadí rout a bezpečnostních middlewarů beze změny** (zmrazené baseline). Opravy nálezů v samostatných commitech: N10 (web build), N2/N2b/N2c (offer worker, sweeper, bezpečný provider), N12 (živé SSE), N4 (desktop admin URL), N1 (ochranné testy).
> Lokálně: pytest 1811 passed, migration_tests 19/19, živé sondy ✔, buildy web/desktop/image ✔, deploy-linux ✔. Report: `docs/architecture/PHASE_B_REPORT.md`, `INTEGRATION_REPORT.md`.

### PR 3 – N9: ORM metadata = schéma z migrací
> **Base:** `refactor/modular-architecture`
>
> Modely doplněny o 97 server defaultů, 15 indexů a model `reconciler_events` přesně podle migrací; test vyžaduje nulový rozdíl autogenerate. Bez nové migrace – produkční schéma ani data se nemění. Lokálně: pytest 1819 passed, migration_tests 19/19. **Blokér nasazení.**
>
> 🤖 Generated with [Claude Code](https://claude.com/claude-code)
