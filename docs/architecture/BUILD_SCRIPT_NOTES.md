# Build skript projektu – technické poznámky

## Kontext

Multi-Agent run #10 (NC-001B) byl zablokován hlášením „not run - the project defines no build Dev Command“. Validační pipeline (BuildProvider::ProjectScript) hledá v kořeni repa `build.bat`, `build.cmd` a `build.sh`. Žádný z nich neexistoval, byl jen `src/desktop/build.bat`.

## Změna

Přidán kořenový `build.bat`. Je to jen orchestrátor existujících buildů, nic neinstaluje ani nekonfiguruje.

| Volání | Co spustí |
|---|---|
| `build.bat` | backend + frontend |
| `build.bat backend` | `src/backend`: `python -m compileall -q app`, `ruff check app/`, `mypy app/`, `lint-imports` (vše přes `.venv`) |
| `build.bat frontend` | `src/frontend`: `npm run build` (`tsc -b && vite build`) |
| `build.bat desktop` | `src/desktop/build.bat` (Qt 6.10.3 + MSVC 2022, napevno nastavené cesty) |
| `build.bat all` | backend + frontend + desktop |

Předpoklady: připravený `src/backend/.venv` a `src/frontend/node_modules` (viz `scripts/bootstrap-dev.ps1`, `npm ci`). Když chybí, skript skončí chybou a návratovým kódem 1. Neznámý cíl vrací 2.

Desktop je mimo výchozí běh, protože vyžaduje konkrétní instalaci Qt a MSVC.

## Validace

- Build: **nespuštěno**. Runtime zamítl `cmd.exe /c build.bat`, protože vyžaduje ruční schválení.
- Testy: nespuštěny.

## Rizika a navazující kroky

- TK-00041 (2026-11-06): `build.bat` i `test.bat` mají CRLF a `.gitattributes` vynucuje `*.bat`/`*.cmd` `eol=crlf`. Oba skripty zatím nikdy neběžely (spuštění čeká na schválení), proto zůstávají necommitnuté. Viz `INTEGRATION_REPORT.md` §8.1.
- Konce řádků (historicky): převod na CRLF runtime zamítl. Při koncích řádků jen LF může `cmd.exe` selhat na návěštích (`call :backend`, `goto`). Doporučení: přidat `*.bat text eol=crlf` do `.gitattributes` a soubor znormalizovat.
- `mypy app/` může na lokálním stroji odhalit chyby, které CI nemá. V tom případě backendová část selže.
- Backendová část nepokrývá bandit ani pip-audit z CI jobu `lint`; ty zůstávají v CI.
- Pokud NovuAI čte Dev Command z nastavení workspace (`.novuai/workspace_context.json`), je potřeba ho nastavit na `build.bat`. Tento soubor nebyl upraven.
