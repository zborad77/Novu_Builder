# Python Backend

Tato slozka je novy cilovy backend pro FotoNabidku.

Smer:

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2
- PostgreSQL
- Redis
- Python AI integrace

Aktualne je pripraveny zaklad vedle puvodniho Node prototypu:

- FastAPI app bootstrap
- settings pres pydantic-settings
- zakladni logging pres structlog
- API router a health endpoint
- SQLAlchemy Base, async session a prvni domenove modely
- modul `projects`
- modul `photos` vcetne local uploadu, primary photo a derivative metadata
- modul `analysis` vcetne mock AI provideru a manualni korekce plochy
- modul `quote-variants` vcetne recalculate logiky a quote items
- kanonicky API kabat `cases / images / analysis-jobs / measurements / estimates / pricebooks`
- Alembic foundation pro databazove migrace

Zamer:

- nebourat fungujici frontendovy prototyp
- postupne prevadet backend moduly
- sjednotit dalsi rust do Python stacku
- drzet stare route jen jako kompatibilni most, nove veci smerovat do kanonicke domeny

Databazovy zaklad:

- dev default bezi na `SQLite`
- cilovy produkcni smer je `PostgreSQL`
- `DATABASE_URL` je async URL pro aplikaci
- `DATABASE_URL_SYNC` je sync URL pro Alembic migrace
- `DB_AUTO_CREATE_SCHEMA=true` je jen dev pohodli pro rychly bootstrap
- `DB_SEED_ON_STARTUP=true` je jen dev seed workflow

Migrační disciplina:

- lokalni dev muze bezet s `DB_AUTO_CREATE_SCHEMA=true`, ale nove modelove zmeny se maji odted zapisovat pres `Alembic`
- pro produkcni nebo sdilene prostredi pocitej s `DB_AUTO_CREATE_SCHEMA=false`
- v produkcnim rezimu ma schema vznikat pres `alembic upgrade head`, ne pres startup aplikace
- `ensure_dev_seed` se ma pouzivat jen v developmentu

Doporucene rezimy:

- `development`
  - `SQLite` nebo lokalni `PostgreSQL`
  - `DB_AUTO_CREATE_SCHEMA=true`
  - `DB_SEED_ON_STARTUP=true`
- `production-like`
  - `PostgreSQL`
  - `DB_AUTO_CREATE_SCHEMA=false`
  - `DB_SEED_ON_STARTUP=false`
  - schema pripravit prikazem `alembic upgrade head`

Zakladni prikazy:

```bash
alembic upgrade head
alembic revision --autogenerate -m "popis_zmeny"
```

Typicky prechod na PostgreSQL:

```bash
# 1. nastav DATABASE_URL a DATABASE_URL_SYNC na PostgreSQL
# 2. vypni DB_AUTO_CREATE_SCHEMA a DB_SEED_ON_STARTUP
# 3. spust migrace
alembic upgrade head
```

## Setup na novem PC

Doporuceny minimalni postup:

```powershell
cd python-backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python tools/import_reference_cases.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Poznamky:

- `import_reference_cases.py` je pro dev/test workflow, ne pro produkci
- pokud nechces testovaci reference, krok s importem muzes preskocit
- bez lokalni `.env` kopie se projekt na novem PC nespusti predvidatelne

Stejny backend setup jde z korene repozitare pripravit i automaticky:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1
```

Nebo s testovacimi referencemi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1 -ImportReferenceCases
```

Bootstrap pro prvni dev start zamerne preskakuje `asyncpg` a `psycopg[binary]`,
protoze lokalni vychozi rezim backendu bezi na `SQLite`.

Po bootstrapu muzes backend z korene repozitare spustit i pres:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-dev.ps1
```

Import testovacich referenci:

```bash
python tools/import_reference_cases.py
```

Skript nacte dataset z `../test-data/reference-cases`, zajisti dev seed zaklad a vytvori z techto referenci testovaci projekty i fotky ve storage.

Nejblizsi dalsi krok:

- dodelat material-catalog a suppliers jako samostatne sluzby
- potom dotahnout auth a export
- nasledne pripravit Redis/background jobs a realne AI providery
