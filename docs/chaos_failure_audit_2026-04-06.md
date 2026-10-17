# Chaos / Failure Audit - 2026-04-06

Rozsah:

- `docs/incident-rehearsal-scenare.md`
- `docs/pilot-operational-resilience-drill.md`
- `docs/operational-load-rehearsal.md`
- `docs/pilot-load-rehearsal.md`
- `python-backend/tests/test_operational_resilience_drill.py`
- `python-backend/tests/test_operational_load_rehearsal.py`
- `python-backend/tests/test_retry_system.py`
- `python-backend/tests/test_r36_stale_job_recovery.py`
- souvisejici readiness / queue / worker / retry implementace

## Executive Summary

Cil tohoto auditu nebyl system "rozbit", ale vyhodnotit, jak dobre umi:

- izolovat jednu poruchu
- degradovat rizene
- zachovat auditovatelny stav
- vratit se do konzistence bez manualnich SQL zasahu
- zachytit problem vcas pres signalizaci

Verdikt:

`partially proven`

Co uz je silne prokazane:

- analysis lane ma dobry lease/reaper/retry recovery model
- retry storm a external API failure storm maji deterministic rehearsal support
- queue saturation ma bounded/backpressure chovani
- Redis/DB/storage outage maji truthy readiness semantics na processing/API vrstve
- worker crash behem jobu ma recovery cestu pres stale-lease reconcile

Co jeste neni dostatecne prokazane:

- live chaos suite ma drift proti aktualni prisnejsi readiness semantice
- host pressure scenare (CPU, memory, disk) nejsou automaticky dokazany
- compound partial outage scenare jsou zatim spis navrzene nez systematicky overene
- alerting coverage pro nektere silence/failure modes je stale neuplna

Nejdulezitejsi zaver:

system uz umi vic "controlled degradation" nez bezny pilot stack, ale confidence neni jeste uplna, protoze plny resilience drill balik neni stale synchronni s novou worker-readiness truth a host-level pressure zustava mimo automatizovanou sadu.

## Dukazy a Overeni

Spustene testy:

```text
pytest python-backend/tests/test_operational_load_rehearsal.py python-backend/tests/test_retry_system.py python-backend/tests/test_r36_stale_job_recovery.py -q
```

Vysledek:

- `22 passed`

Spustene deterministic resilience drill testy:

```text
pytest python-backend/tests/test_operational_resilience_drill.py -q
```

Vysledek:

- `2 passed`
- `3 failed`

Interpretace failu:

- failnute testy stale ocekavaji `/ready == 200` po recovery i bez ziveho worker heartbeat
- aktualni implementace je prisnejsi a vraci `503`, dokud worker neni realne ready

To je dulezity zaver sam o sobe:

- nejde o dukaz domino selhani
- je to dukaz driftu mezi chaos suite a aktualnim safety kontraktem

## 1. Scenario Matrix

### 1. Redis outage / restart

Stav:

- popsano v `docs/incident-rehearsal-scenare.md`
- popsano v `docs/pilot-operational-resilience-drill.md`
- automaticky overeno v `test_operational_resilience_drill.py`

Co je prokazano:

- strict processing readiness pada na `503`
- `queueState` prechazi do `unavailable`
- po recovery se processing readiness umi vratit do `ready`

Bezpecnostni hodnoceni:

- jedna porucha neshodi cele API plane okamzite
- degradace je rizena hlavne na processing plane
- recovery confidence pro analysis lane je dobra

Residualni riziko:

- auth/cache/queue stale sdileji stejny Redis failure domain
- alerting pro monitoring blindness a nektere Redis-specific silence modes neni jeste dost tvrdy

Hodnoceni:

`good with shared-failure-domain risk`

### 2. DB latency spike / reconnect

Stav:

- scenario je detailne navrzene v docs
- deterministic testy pokryvaji DB outage/recovery, ne plny latency chaos

Co je prokazano:

- pri DB outage pada `/ready`
- po obnoveni DB probe cesta umi znovu fungovat
- worker a API maji oddelene DB pooly, coz tlumi domino efekt

Co neni prokazano:

- host-level nebo realny DB latency spike pod zatizenim
- lock wait / session pressure / pool starvation v live drill automatizaci

Bezpecnostni hodnoceni:

- reconnect / hard outage chovani je slusne
- cista latency degradace je jen castecne pokryta symptomaticky

Hodnoceni:

`partially proven`

### 3. Worker crash behem jobu

Stav:

- velmi dobre pokryto testy
- stale-lease recovery v `test_r36_stale_job_recovery.py`
- worker restart / leased-job recovery v `test_operational_resilience_drill.py`

Co je prokazano:

- job se nema ztratit
- expired lease se vraci do `queued`
- reaper recovery respektuje DB truth
- stary lease neprebije novy heartbeat/renew

Bezpecnostni hodnoceni:

- analysis lane ma silny anti-domino kontrakt
- recovery je auditovatelna a deterministicka

Residualni riziko:

- heavy/photo lane nema stejne silny recovery kontrakt jako analysis lane

Hodnoceni:

`strongly proven for analysis lane`

### 4. Backend restart pod loadem

Stav:

- scenario popsano v live drill docs
- deterministic test stale existuje, ale failuje na zastaralem ocekavani `/ready`

Co je prokazano:

- auth flow po restartu backendu ma byt recoverable
- public health zůstava truthy

Co audit odhalil:

- plny confidence je dnes snizeny driftujici test suite
- system je ted prisnejsi: bez worker heartbeat neda `ready`

To je z pohledu safety spis plus nez minus, ale chaos suite to musi respektovat.

Hodnoceni:

`safety-improved but rehearsal suite stale`

### 5. Storage timeout / failure

Stav:

- scenario popsano v docs
- deterministic test existuje v resilience drill

Co je prokazano:

- storage outage se projevi v readiness
- flow nema selhavat tise
- po obnoveni dependency se system umi vratit

Omezeni:

- testy overuji outage/recovery path, ne pomalou storage latenci pod realnym zatizenim
- host/network level storage timeout storm neni simulovan externim toxiproxy nebo egress shaping

Hodnoceni:

`partially proven`

### 6. External API failure storm

Stav:

- velmi dobre navrzene rehearsal markery v mock provideru
- `test_operational_load_rehearsal.py` potvrzuje deterministic failure markery
- `test_retry_system.py` potvrzuje retry vs DLQ rozhodovani

Co je prokazano:

- provider failure lze bezpečne a opakovatelne simulovat
- retry ma budget a backoff
- exhausted budget jde do dead-letter, ne do nekonecneho running stavu
- API plane muze zustat oddeleny od background processing incidentu

To je presne anti-domino chovani, ktere chceme.

Hodnoceni:

`well proven`

### 7. Retry storm

Stav:

- docs maji explicitni rehearsal scenar
- `test_retry_system.py` prokazuje bounded retry chovani
- `run-operational-load-rehearsal.py` umi retry storm phase

Co je prokazano:

- deterministic jitter rozprostira retry v case
- max attempts jsou bounded
- retry inflight budget je enforceovany
- terminal path umi dead-letter fallback

Omezeni:

- automatizovany live proof neoveruje skutecny host-level resource tlak z retry burstu
- alert coverage kolem retry pressure je stale potreba dotahnout

Hodnoceni:

`good core, partial live proof`

### 8. Queue saturation

Stav:

- docs i load rehearsal skript maji explicitni saturacni fazi
- load resilience audit uz driv identifikoval bounded queue/backpressure kontrakt

Co je prokazano:

- bounded queue depth
- `429` backpressure misto silent overloadu
- queued/running/backpressure signaly jsou vystavene pres internal health a metrics

Omezeni:

- skutecny host pressure nebo 50+ tenant live saturation nebyly zde fyzicky pousteny
- heavy lane saturation neni stejne silne overena jako analysis lane

Hodnoceni:

`partially proven but architecturally sound`

### 9. Partial dependency outage

Stav:

- jednotlive partial outage scenare jsou popsane a cast testovana:
  Redis
  DB
  storage

Co je prokazano:

- jedna zavislost nemusi shodit vsechno
- readiness umí odlisit API plane a processing plane

Co neni prokazano:

- slozene partial outages:
  Redis degraded + worker stale
  DB latency + external API failure
  storage timeout + queue backlog

Hodnoceni:

`partially proven`

### 10. Disk / memory / CPU pressure

Stav:

- docs explicitne rikaji, ze to backend HTTP diagnostika sama neprokazuje
- v repu neni automatizovany chaos suite pro host resource pressure

Co je relevantni:

- je to relevantni pro realnou robustnost
- ale neni to bezpecne ani smysluplne simulovat jen uvnitr teto app vrstvy bez node telemetry

Co je dnes neprokazane:

- runaway memory pri upload/load
- CPU saturation pri heavy path
- disk pressure vliv na storage/export behavior

Hodnoceni:

`not proven`

## 2. Co Je Skutecne Robustni

### Analysis lane recovery

To je dnes nejsilnejsi cast celeho failure modelu:

- DB authoritative job truth
- Redis transport truth jen pro orchestration
- lease ownership guard
- stale-lease reconcile
- bounded retry
- DLQ fallback

To je dobra ochrana proti domino efektu pri worker crashi i provider failure stormu.

### Controlled degradation pres probes

Silna cast:

- `/ready/processing?strict=1` uz nelze snadno "ozelenit" bez skutecneho worker/queue zdraví
- storage/DB/Redis outage se umi promítnout do readiness

I kdyz to rozbilo par starsich test assumptions, z pohledu safety je to spravne.

### Failure isolation mezi API a background processing

External API failure storm a retry storm jsou izolovane primarne do background path:

- CRUD/auth flow nemusi padat spolu s provider incidentem
- to je velmi dobra anti-domino vlastnost

## 3. Kde Jsou Mezery

### G1 [P0] Chaos suite ma drift proti aktualni safety truth

`test_operational_resilience_drill.py` stale predpoklada "green ready" i bez worker heartbeat.

To je dnes neplatne. Dokud se tato sada nesrovna s aktualnim readiness kontraktem, neni recovery confidence plne udrzovany automaticky.

### G2 [P0] Host pressure neni prokazany

Chybi overeni:

- CPU pressure
- memory pressure
- disk pressure
- real Redis/Postgres node pressure

To je nejvetsi neoverena cast "stability under load + failure".

### G3 [P1] Compound partial failures nejsou systematicky automatizovane

Chybi matrix typu:

- Redis degraded + auth traffic
- DB latency + worker retry storm
- storage timeout + export burst
- backend restart behem queue saturation

### G4 [P1] Heavy/photo lane nema stejnou confidence jako analysis lane

Analysis lane je dobre podlozeny testy.
Heavy/photo lane ma vic dokumentovaneho zameru nez plne stejne silnou recovery dokazatelnost.

### G5 [P1] Alert capture neni soucasti deterministickeho drill loopu

Docs spravne rikaji "zapsat, ktere alerty se skutecne spustily", ale v automatizovanem test baliku to zatim neni first-class assertion.

### G6 [P2] Live load scripts umi provozni truth, ale ne hardware truth

`run-operational-load-rehearsal.py` umi:

- auth burst
- CRUD burst
- queue throughput
- retry storm
- tenant fairness
- sustained load

Sam ale explicitne priznava, ze neprokazuje:

- host CPU saturation
- host memory growth
- direct PostgreSQL pressure
- direct Redis pressure

## 4. Doporucena Bezpecna Chaos Sada

### P0 sada - musi byt green pred pilot confidence claim

1. Redis restart behem queue load
   Pass:
   `jobProcessingReady=false`, zadna ztrata job truth, recovery bez SQL zasahu.

2. Worker crash behem leased jobu
   Pass:
   zadny lost job, stale lease -> queued, presne jeden terminal outcome.

3. External API failure storm
   Pass:
   bounded retry, DLQ fallback, CRUD/auth stale usable.

4. Queue saturation
   Pass:
   `429`/backpressure, ne silent overload nebo `500`.

5. Backend restart pod auth + read load
   Pass:
   auth session recoverable, `/ready` truthy podle worker reality, zadna ticha nekonzistence.

### P1 sada - musi byt green pred vyssim operational confidence

1. DB latency spike pod queue load
2. Storage timeout storm
3. Partial dependency outage kombinace
4. Retry storm + tenant fairness
5. Alert assertion layer:
   kazdy chaos scenar musi zaznamenat, jestli vznikl odpovidajici alert

### P2 sada - host/system pressure

1. CPU pressure pres host tooling
2. Memory pressure pres host tooling
3. Disk pressure rehearsal
4. Redis/Postgres pressure pres toxiproxy / tc / node exporter telemetry

Tyto scenare nedoporucuji simulovat uvnitr beziciho pilot hostu bez staging izolace.

## 5. Navrh Pass/Fail Invariantu

Kazdy chaos scenar ma prochazet jen tehdy, kdyz plati vsechny:

### Safety

- zadna ztrata job truth
- zadna ticha ztrata audit truth
- zadna falesne zelena readiness

### Isolation

- jedna porucha neshodi auth, CRUD a background processing zaraz, pokud to neni sdilena zavislost
- provider failure storm nezpusobi total API meltdown

### Recovery

- po navratu dependency neni potreba manualni SQL zasah
- system se vrati do konzistence v predvidatelnem case

### Auditability

- problem je videt v probe payload nebo metrics
- incident ma odpovidajici structured logy
- alerting problem zachyti, nebo je explicitne oznacen jako blind spot

## 6. Priority Fixu P0-P3

### P0

1. Opravit `test_operational_resilience_drill.py` podle aktualni worker-readiness truth.
2. Udelat z resilience drill sady povinny release gate pro restart/outage scenare.
3. Doplniť alert assertions nebo aspon strojove citelne rehearsal artifacty o "alert expected / observed".

### P1

1. Dopsat compound partial outage matrix.
2. Dopsat heavy/photo recovery confidence scenare.
3. Dopsat DB latency a storage timeout rehearsal do automatizovatelne podoby.

### P2

1. Zavest host pressure staging drills s node telemetry.
2. Navazat chaos rehearsals na dashboard snapshots a post-incident artifact export.

### P3

1. Pravidelne rehearsal cadence:
   tydenni deterministic suite,
   mesicni live outage drill,
   kvartalni host pressure drill.

## 7. Verdikt

`partially proven`

Prakticka interpretace:

- controlled degradation je pro analysis/queue/provider failure uz dost dobre navrzena a z velke casti i dokazatelna
- anti-domino chovani existuje, hlavne mezi CRUD/auth a background failure stormy
- recovery confidence je slusna pro analysis lane, ale jeste ne pro cely system ve vsech typech poruch

Takze:

- pro pilot-level resilience je zaklad dobry
- pro tvrzeni "mame skutecne overenou robustnost pri chaos/failure scenarich" jeste chybi srovnat suite s aktualni readiness truth a doplnit host/compound failure vrstvu
