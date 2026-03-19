# FotoNabidka / NOVU Builder

Tento repozitar je zacatek produktu pro rychlou tvorbu cenovych nabidek ve stavebnictvi.

Aktualni smer projektu:

- mobilni aplikace pro sber vstupu v terenu
- server pro AI analyzu, vypocty a generovani dokumentu
- kancelarska webova aplikace pro kontrolu, editaci a odeslani nabidky

Podrobny navrh je v dokumentu [docs/fotonabidka-blueprint.md](docs/fotonabidka-blueprint.md).
Prakticke rozdeleni mezi desktop, server a AI vrstvu je v [docs/runtime-responsibilities.md](docs/runtime-responsibilities.md).
Reset do noveho ciloveho backend smeru je v [docs/final-architecture-reset.md](docs/final-architecture-reset.md).

## Aktualni stav repozitare

Repo dnes obsahuje uz jen aktivni vetve projektu:

- `desktop-qt` - novy cilovy desktop klient v C++/Qt6
- `novu-react` - aktualni React prototyp pro kancelarsky frontend
- `python-backend` - novy cilovy backend smer (FastAPI)
- `docs` - architektura, blueprint a provozni poznamky
- `storage` - lokalni dev storage pro obrazky a exporty

## Doporucena architektura MVP

- mobil: React Native + Expo + TypeScript
- kancelar: C++ + Qt6 Widgets
- backend API: Python + FastAPI
- AI worker: Python
- databaze: PostgreSQL
- fronty: Redis
- uloziste: S3 kompatibilni storage

## Lokalni spusteni soucasnych prototypu

Backend `python-backend`:

```bash
npm run api:dev
```

Frontend `novu-react`:

```bash
npm run web:dev
```

Desktop skeleton `desktop-qt`:

- zatim jen kostra aplikace a architektury
- Qt6 build a API napojeni doplnime v dalsich krocich

Lint frontend:

```bash
npm run web:lint
```

## Nove PC / onboard krok za krokem

Pokud chces pokracovat na jinem PC po prihlaseni na svuj GitHub, je to mozne.
Git ti prenese kod a verzovane soubory, ale ne lokalni databazi, build slozky,
`storage`, tajne klice ani necommitnute zmeny.

### Co je potreba mit na druhem PC

- `Git`
- `Python 3.12+`
- `Qt 6.x` + `Qt Creator`
- `Visual Studio 2022 Build Tools` nebo plne VS s `MSVC`
- doporucene: `PowerShell 7+` nebo bezny Windows PowerShell

### Zakladni postup

```powershell
git clone https://github.com/zborad77/Novu_Builder.git
cd Novu_Builder
```

Pak doporuceny onboarding:

1. backend setup v [python-backend/README.md](python-backend/README.md)
2. desktop setup v [desktop-qt/README.md](desktop-qt/README.md)
3. volitelne import testovacich referenci z `test-data/reference-cases`

### Rychly setup check

Na Windows muzes pustit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-check.ps1
```

Skript zkontroluje:

- `git`
- `python`
- `cmake`
- `qtpaths` nebo `qmake`
- `MSVC` build shell indikatory

Je to jen rychla orientacni kontrola pred dalsim setupem.

### Automaticky dev bootstrap

Pro rychle pripraveny backend setup na novem PC muzes pustit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1
```

Pokud chces rovnou naimportovat i testovaci reference:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1 -ImportReferenceCases
```

Bootstrap pripravi:

- `python-backend/.venv`
- backend zavislosti z `requirements.txt`
- `.env` z `.env.example`, pokud chybi
- Alembic migrace
- volitelne testovaci reference

Pro prvni dev start bootstrap zamerne preskakuje PostgreSQL drivery `asyncpg` a `psycopg[binary]`,
protoze vychozi lokalni rezim bezi na `SQLite`.

### Rychly start backendu

Po bootstrapu muzes backend spustit jednim prikazem:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Pro bezpecne overeni bez spusteni procesu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1 -DryRun
```

## Nejblizsi kroky

1. Rozvijet `desktop-qt` jako cilovy kancelarsky klient.
2. Dovest Python backend ke stabilnimu produkcnimu API tvaru.
3. React ponechat jen jako referencni prototyp workflow a obrazovek.
