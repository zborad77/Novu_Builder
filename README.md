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

Repo dnes obsahuje nekolik prototypu:

- `novu-react` - aktualni React prototyp pro kancelarsky frontend
- `server` - puvodni Node.js backend prototyp, uz jen jako referencni most
- `python-backend` - novy cilovy backend smer (FastAPI)
- `mobile_app` - zatim jen prazdny nacrt
- `desktop_app` - starsi staticky prototyp
- `shared` - prazdne nebo nedokoncene sdilene soubory

Pro dalsi vyvoj budeme stavajici prototypy postupne sjednocovat, ne vse zahazovat najednou.

## Doporucena architektura MVP

- mobil: React Native + Expo + TypeScript
- kancelar: React + TypeScript
- backend API: Node.js + TypeScript
- AI worker: Python + FastAPI
- databaze: PostgreSQL
- fronty: Redis
- uloziste: S3 kompatibilni storage

## Lokalni spusteni soucasnych prototypu

Backend:

```bash
npm start
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

1. Sjednotit datovy model a API kolem projektu, fotek a AI vysledku.
2. Vybudovat prvni end-to-end tok: vytvorit projekt -> nahrat fotky -> zobrazit zpracovani v kancelari.
3. Teprve potom doplnovat mereni plochy, pricing engine a generovani dokumentu.
