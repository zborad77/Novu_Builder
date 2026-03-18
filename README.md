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

- `novu-react` - aktualni React prototyp pro kancelarsky frontend
- `python-backend` - novy cilovy backend smer (FastAPI)
- `docs` - architektura, blueprint a provozni poznamky
- `storage` - lokalni dev storage pro obrazky a exporty

## Doporucena architektura MVP

- mobil: React Native + Expo + TypeScript
- kancelar: React + TypeScript
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

Lint frontend:

```bash
npm run web:lint
```

## Nejblizsi kroky

1. Dodelat cisteni prezencni vrstvy a UX kancelarskeho rozhrani.
2. Dovest Python backend ke stabilnimu produkcnimu API tvaru.
3. Potom doplnovat auth, exporty, realne AI providery a mobilni klient.
