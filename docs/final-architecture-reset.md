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
- `desktop kancelar` jako review, edit a schvalovaci pracoviste
- `Python + FastAPI` jako centralni backend a orchestrator
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

Tyto casti jsme pouzili pro migraci, ale uz nejsou soucasti aktivniho smeru:

- puvodni `server/` Node.js backend
- SQLite jako hlavni cesta pro budouci produkci
- dalsi rozvoj backendu v plain JavaScriptu

To neznamena, ze jsou spatne.
Jen uz nejsou cilovy technologicky smer.

## 4. Novy cilovy runtime

### 4.1 Mobil

- samostatna mobilni aplikace
- hlavni vstup od technika
- foto, GPS, kratky popis, odeslani
- bez business logiky, ceniku a rozhodovacich pravidel

### 4.2 Desktop kancelar

- hlavni pracovni plocha pro kalkulanta a managera
- kontrola serveroveho vystupu
- editace textu a cisel
- schvaleni finalni nabidky
- bez vlastni business logiky a bez autoritativnich vypoctu

### 4.3 Backend

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2
- structlog
- PostgreSQL
- Redis
- jediny zdroj business pravdy
- jedine misto pro workflow pravidla, ceniky, dodavatele a firmy

### 4.4 AI vrstva

- Python sluzby nebo Python worker
- CV / vision analyza
- AI navrh materialu a workflow
- segmentace a area estimation
- backend ji orchestruje a uklada jeji vystupy

## 5. Jak jsme migrovali

Nepouzili jsme velky jednorazovy rewrite.

Postup byl:

1. zalozit `python-backend/`
2. prevest zakladni moduly
3. prepojit React kancelar na FastAPI
4. odstranit legacy JS backend a stare prototypy

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
- legacy JS backend uz dal nerozsirujeme
- klienti jen zobrazuji, odesilaji a potvrzuji
- business logika, workflow rozhodovani a AI orchestrace patri jen na backend

Toto je novy cilovy kabat projektu.
