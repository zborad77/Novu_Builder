# Final Architecture Reset

Tento dokument rika, jak projekt preklapime ze soucasneho prototypu do noveho ciloveho kabatu.

Nejde o zahazovani dosavadni prace.
Jde o sjednoceni dalsiho vyvoje do smeru, kteremu verime dlouhodobe.

## 1. Proc delame reset smeru

Dosavadni prototyp nam pomohl overit:

- produktovy tok
- datovy model
- cenovou logiku
- UX kancelarske casti
- AI pipeline jako koncept

Ale dalsi vyvoj uz chceme vest jinou backendovou cestou.

Novy cil:

- `mobilni aplikace` jako primarni vstup v terenu
- `web / desktop kancelar` pro kalkulaci, editaci a administraci
- `Python + FastAPI` jako backend
- `PostgreSQL` jako hlavni databaze
- `Redis` pro fronty a async ulohy
- `Python` i pro AI a vision vrstvu

## 2. Co zustava

Tyto casti jsou porad platne a maji hodnotu:

- React kancelarsky frontend jako produktovy prototyp
- workflow projektu
- model projektu, fotek, analyz a variant
- firemni cenik a dodavatele
- pricing logika
- pravidla pro manualni plochu a referencni fotku
- myslenka `original / preview / ai_input` pro fotky
- dokumentace produktu a MVP

Jinymi slovy:

- logika zustava
- backendovy kabat se meni

## 3. Co uz neni cilovy smer

Tyto casti bereme dal jen jako prechodovy prototyp:

- `server/` Node.js backend
- SQLite jako hlavni cesta pro budouci produkci
- dalsi rozvoj backendu v plain JavaScriptu

To neznamena, ze jsou spatne.
Jen uz nejsou cilovy technologicky smer.

## 4. Novy cilovy runtime

### 4.1 Mobil

- samostatna mobilni aplikace
- hlavni vstup od technika
- foto, GPS, kratky popis, odeslani

### 4.2 Kancelarsky web

- React
- hlavni pracovni plocha pro kalkulanta a managera
- editace, kontrola, prepocet, dokumenty, admin

### 4.3 Backend

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2
- structlog
- PostgreSQL
- Redis

### 4.4 AI vrstva

- Python sluzby nebo Python worker
- CV / vision analyza
- AI navrh materialu a workflow
- segmentace a area estimation

## 5. Jak budeme migrovat

Nebudeme delat velky jednorazovy rewrite.

Budeme postupovat vedle sebe:

1. Node backend zustane jako referencni prototyp
2. zalozime `python-backend/`
3. prevedeme postupne zakladni moduly
4. frontend pozdeji prepojime na nove FastAPI endpointy
5. Node backend pak pujde archivovat

## 6. Poradi prevodu modulu

Doporucene poradi:

1. `health + config + app bootstrap`
2. `projects`
3. `photos`
4. `analysis`
5. `quote variants`
6. `material catalog`
7. `suppliers`
8. `auth`
9. `documents`
10. `email`

To znamena:

- nejdriv postavime stejnou kostru
- teprve potom budeme znovu pridavat dalsi funkce

## 7. Co je ted dalsi spravny krok

Bezprostredne po tomto resetu:

1. zalozit minimalni FastAPI skeleton
2. definovat settings a strukturu modulu
3. pridat health endpoint
4. pripravit SQLAlchemy modely podle dnesniho datoveho modelu

## 8. Pravidlo pro dalsi vyvoj

Od teto chvile:

- nove backendove moduly patri do `python-backend/`
- `server/` slouzi uz jen jako docasny referencni prototyp
- React frontend zatim muzeme nechat bez velkeho bourani

Toto je novy cilovy kabat projektu.
