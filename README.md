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

Repo dnes obsahuje tyto hlavni slozky:

- `desktop-qt` - novy cilovy desktop klient v C++/Qt6
- `python-backend` - novy cilovy backend smer (FastAPI)
- `docs` - architektura, blueprint a provozni poznamky
- `storage` - lokalni dev storage pro obrazky a exporty. Local storage is DEV ONLY.

## Doporucena architektura MVP

- mobil: React Native + Expo + TypeScript
- kancelar: C++ + Qt6 Widgets
- backend API: Python + FastAPI
- AI worker: Python
- databaze: PostgreSQL
- fronty: Redis
- uloziste: S3 kompatibilni storage

## Lokalni spusteni aktivnich casti

Backend `python-backend`:

```bash
npm run api:dev
```

Desktop skeleton `desktop-qt`:

- zatim jen kostra aplikace a architektury
- Qt6 build a API napojeni doplnime v dalsich krocich

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

### Prepnuti backendu na PostgreSQL

Pokud chces lokalni backend prepnout ze `SQLite` na `PostgreSQL`, muzes pouzit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch-backend-db.ps1 -Target postgres
```

S vlastnimi prihlasovacimi udaji a rovnou s migracemi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch-backend-db.ps1 `
  -Target postgres `
  -PostgresHost localhost `
  -PostgresPort 5432 `
  -PostgresDatabase novu_builder `
  -PostgresUser novu `
  -PostgresPassword novu `
  -RunMigrations
```

Skript:

- upravi `python-backend/.env`
- pri PostgreSQL doinstaluje chybejici `asyncpg` a `psycopg[binary]`
- umi rovnou spustit `alembic upgrade head`

Navrat zpet na `SQLite`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch-backend-db.ps1 -Target sqlite
```

### Rychly start backendu

Po bootstrapu muzes backend spustit jednim prikazem:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Pro bezpecne overeni bez spusteni procesu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1 -DryRun
```

## Production compose env

Production `docker compose` startup expects a filled root
[.env.production.example](.env.production.example) copy with at least:

- `APP_BASE_URL`
- `CORS_ALLOWED_ORIGINS`
- `METRICS_AUTH_TOKEN`
- `STORAGE_BACKEND=s3`
- `STORAGE_AUTHORITATIVE=true`
- `S3_CONNECT_TIMEOUT_SECONDS>0`
- `S3_READ_TIMEOUT_SECONDS>0`
- `STORAGE_SIGNED_URL_TTL_SECONDS<=3600`
- `EXPORT_TTL_DAYS=7`
- `S3_BUCKET`
- `S3_REGION`

V produkci se media i exporty cti a zapisuji pres storage key v aktivnim
storage backendu. API vraci pouze casove omezené signed URL; zadny endpoint
nesmi vracet raw public S3 URL. Local storage is DEV ONLY. Lokalni `storage_data` a `/mock-storage`
zustavaji jen pro DEV/TEST.
Upload flow je jednotny: `multipart/form-data` -> backend validace skutecnych
bajtu souboru -> zapis do aktivniho storage backendu. Metadata-only JSON upload
neni podporovan.
Orphan management je dostupny pres `storage_consistency_service`: scan porovnava
DB/photo a DB/export reference proti storage keyum, `cleanup_orphans()`
bezi defaultne v safe mode a kazdou akci strukturovane loguje.
Export metadata jsou authoritative v DB a kazdy export ma `expires_at`; worker
prubezne maze expirovane export artefakty ze storage podle `EXPORT_TTL_DAYS`.

Deployment details and the operator checklist are in [DEPLOY.md](DEPLOY.md).

## Nejblizsi kroky

1. Rozvijet `desktop-qt` jako cilovy kancelarsky klient.
2. Dovest Python backend ke stabilnimu produkcnimu API tvaru.

## Architektura klientu a APP_BASE_URL

Web klient neni soucasti aktualni architektury.
Primarnim klientem je desktopova Qt aplikace (`desktop-qt`).
Self-service reset hesla vyzaduje externi web klient dostupny pres `APP_BASE_URL` —
dokud zadny takovy klient neexistuje, endpointy `/forgot-password` a `/reset-password` zustavaji vypnute (HTTP 410 Gone).

## TODO: Auth cleanup (technical debt)

POST /api/v1/auth/change-password aktuálně ověřuje staré heslo přes `AuthService.login()`.

Důsledek:
- při ověření se zbytečně generují access/refresh tokeny
- tokeny nejsou použity ani vráceny
- není to bezpečnostní problém, ale architektonicky nečisté

Plán do budoucna:
- přidat do `AuthService` metodu např. `verify_password(user_id, plain_password) -> bool`
- použít ji místo `login()` v change-password endpointu
- oddělit ověřování hesla od generování tokenů

Priorita: nízká (neblokuje funkčnost ani bezpečnost)
