# Navrh Orchestrace pro NOVU Builder

## Proc tento navrh

NOVU Builder uz ma dobre zaklady pro orchestrace:

- backend je explicitne definovany jako centralni orchestrator
- existuje stavovy automat zakazky v `app/case_workflow/transitions.py`
- analysis lane uz bezi pres Redis lease queue + DB-authoritative lifecycle
- heavy lane uz pokryva exporty a photo processing
- desktop uz ma realtime smer pres `ws/case-activity`

Chybi ale jeden sjednoceny navrh, ktery rekne:

- co je synchronni command flow
- co je asynchronni side effect
- co je autoritativni stav v DB
- ktere udalosti maji byt publikovany do realtime streamu
- jak maji na sebe navazovat `analysis`, `quote recalculation`, `proposal`, `export`

Cilem tohoto dokumentu je doplnit prave tuto orchestration vrstvu bez zbytecneho prepisu existujici architektury.

## 1. Hlavni principy

Navrhuji drzet techto 8 pravidel:

1. `PostgreSQL` je jediny autoritativni stav business workflow.
2. `Redis` je pouze orchestration transport pro async praci, nikdy ne zdroj pravdy.
3. Kazda uzivatelska akce je `command`, ne primy "volny update statusu".
4. Kazdy command nejdriv zapise autoritativni stav do DB a az potom publikuje side effect.
5. Dlouhe nebo drahe operace musi jit do queue lane, ne do request handleru.
6. Kazdy async job musi byt idempotentni a obnovitelny po restartu workeru.
7. Realtime websocket nema byt dalsi business vrstva, jen projekce autoritativniho stavu.
8. Klienti mohou iniciovat workflow, ale nesmi rozhodovat o finalnim obchodnim vysledku.

## 2. Doporuceny orchestration model

Doporucuji rozdelit orchestrace do 4 vrstev:

### A. Command orchestration

Vstupni vrstva pro user-driven akce:

- `create_case`
- `upload_photos`
- `submit_case`
- `start_analysis`
- `confirm_work_items`
- `request_quote_recalculation`
- `approve_proposal`
- `create_final_proposal`
- `send_quote`
- `archive_case`

Tato vrstva patri do API route + service + `case_workflow` effectu.

### B. Domain orchestration

Vrstva, ktera rozhoduje:

- jestli je akce povolena
- jaky je dalsi stav zakazky
- jake side effecty se maji naplanovat
- jestli jde o synchronni prepocet nebo async job

Sem patri hlavne:

- `ProjectService`
- `AnalysisService`
- `CaseActionService`
- `ProposalDraftService`
- `QuoteVariantService`
- `ExportService`
- `WorkCatalogService`

### C. Async orchestration

Vrstva pro planovani a zpracovani delsi prace:

- `analysis` lane
- `heavy` lane
- retry
- DLQ
- startup reconciliation
- stale lease recovery

Sem patri stavajici `worker.queue`, `worker.heavy_queue`, `worker.runner`.

### D. Projection orchestration

Vrstva pro to, co vidi klient:

- `ProjectDetail.workflowStatus`
- `availableTransitions`
- `case-activity` websocket stream
- admin/job status pohledy

Tohle neni misto pro business rozhodovani, ale pro citelne promiceni stavu.

## 3. Doporuceny hlavni workflow

Navrhuji povazovat za referencni backbone tento tok:

`draft -> intake -> analyzing -> proposal_ready -> quote_ready -> sent -> archived`

Vedlejsi odchylky:

- navrat do `draft`
- `cancelled`
- doplnkove reruny `analysis`
- doplnkove `quote_recalculation`
- opakovane generovani exportu

To uz dnes v projektu z velke casti existuje. Doporucuji ho jen formalne povysit na hlavni orchestration osu.

## 4. Stavova masina a side effecty

Doporucena mapa orchestrace na case status:

### `draft`

Povolene commandy:

- editace metadat zakazky
- upload a mazani fotek
- volba primary/reference photo
- doplnovani runtime work items

Zakazane:

- odeslani nabidky
- archivace

### `intake`

Povolene:

- finalni kontrola vstupu
- `start_analysis`

Side effect pri `start_analysis`:

- zalozit `AnalysisJob(status=queued)`
- po commitu enqueue do `analysis` lane
- publikovat websocket event `analysis_job_queued`

### `analyzing`

Povolene:

- sledovani prubehu
- pripadny cancel nebo navrat do `draft`

Worker side effect:

- analysis worker dokonci vision pipeline
- ulozi `AnalysisResult`
- zalozi nebo znovu pouzije `quote_recalculation` job
- po uspesnem vyhodnoceni prepne case do `proposal_ready`

Doporuceni:

- transition `analyzing -> proposal_ready` nema byt rozptylen po vice routach
- ma byt provedena jednou orchestration metodou po potvrzeni, ze:
  - existuje platny `AnalysisResult`
  - probehl quote recalculation
  - existuje `proposal_draft`

### `proposal_ready`

Povolene:

- review AI navrhu
- manualni korekce work item values
- opakovany prepocet
- approve proposal

Side effecty:

- manualni potvrzeni/correction value muze vyvolat `quote_recalculation`
- `approve_proposal` ma uzamknout pricing snapshot a prepnout do `quote_ready`

### `quote_ready`

Povolene:

- finalni kontrola textu a ceny
- `send_quote`

Side effect pri `send_quote`:

- vytvorit `ProjectExport(quote-pdf, pending)`
- enqueue do `heavy` lane
- publikovat websocket event `export_queued`
- po vytvoreni exportu doplnit eventualni email side effect

### `sent`

Povolene:

- cteni historie
- opakovany export
- archivace

Side effect pri `archive_case`:

- vytvorit `ProjectExport(case-zip, pending)`
- enqueue do `heavy` lane

### `archived` / `cancelled`

Pouze read-only nebo explicitne omezeny administrativni rezim.

## 5. Rozdeleni queue lanes

Soucasne rozdeleni na `analysis` a `heavy` lane je spravne. Doporucuji ho zachovat a jen presneji pojmenovat odpovednosti.

### `analysis` lane

Patri sem:

- vision analysis
- follow-up `quote_recalculation`
- lehke navazne business prepocitani

Nepatri sem:

- exporty
- resize/variant processing fotek
- dlouhe IO-heavy ulohy

### `heavy` lane

Patri sem:

- `photo_variant_processing`
- `export_generate`
- budouci bulk import/export
- budouci OCR batch nebo document assembly, pokud bude draha

### Doporuceni navic

Nepresouval bych `quote_recalculation` do heavy lane, dokud realne neni IO-heavy. Dava smysl drzet ho blizko analysis lifecycle, protoze je to primy nasledny business krok po analyze.

## 6. Doporucena command-to-job orchestrace

Doporuceny kanonicky sled:

1. User command prijde do API.
2. API overi auth, tenant scope a payload.
3. Domain service provede guardy a zapise autoritativni zmenu do DB.
4. V ramci transaction se ulozi i "planned side effect marker", typicky job row nebo export row.
5. Po commitu se side effect enqueue do Redis.
6. Worker provede async praci.
7. Worker zapise finalni vysledek opet do DB.
8. Projection vrstva zmeni `workflowStatus`, `availableTransitions` a websocket stream.

Tohle presne odpovida tomu, co uz je ted dobre rozjete v `case_workflow/action_effects.py`, a doporucuji tenhle model rozsirit i na dalsi commandy mimo status transitions.

## 7. Realtime orchestrace

Pro `case_activity_ws` doporucuji pouzivat jednotny event envelope:

```json
{
  "eventId": "evt_123",
  "caseId": "prj_123",
  "eventType": "analysis_job_completed",
  "occurredAt": "2026-04-21T10:30:00Z",
  "sequence": 1042,
  "payload": {}
}
```

Minimalni katalog eventu:

- `case_status_changed`
- `photo_uploaded`
- `photo_processing_started`
- `photo_processing_completed`
- `analysis_job_queued`
- `analysis_job_started`
- `analysis_job_retry_scheduled`
- `analysis_job_completed`
- `analysis_job_failed`
- `quote_recalculation_queued`
- `quote_recalculation_completed`
- `proposal_draft_updated`
- `final_proposal_created`
- `export_queued`
- `export_completed`
- `export_failed`

Dulezite:

- websocket event nema byt jediny zdroj informace
- klient po eventu muze refetchovat detail nebo patchnout lokalni stav
- event musi jit vzdy od autoritativni DB zmeny, ne od "best guess" z klienta

## 8. Orchestrace nad work catalog runtime

`runtime_workflow_subsystem` uz ma dobry smer a mel by byt brany jako operacni vrstva mezi analyze a pricing.

Doporucuji tento sled:

1. `analysis` vrati work type suggestion + detection evidence
2. backend zalozi nebo aktualizuje `ProjectWorkItem`
3. vision vyplni `ProjectWorkItemValue(source_type=vision, confirmation_status=pending)`
4. operator potvrdi nebo opravi hodnoty
5. potvrzena runtime data se stavaji vstupem pro pricing
6. `quote_recalculation` pracuje jen nad tenant-effective runtime snapshotem

Toto je dulezite, protoze to oddeluje:

- AI navrh
- operator review
- obchodni vypocet

Prave tady bude dlouhodobe hlavni hodnota orchestrace.

## 9. Idempotence a recovery

Tady uz je projekt silny a navrh doporucuje na tom stavet dal:

- DB status je authoritative
- Redis lease je jen transport
- startup reconciliation vraci ztracene joby zpet do fronty
- stale lease se requeue nebo dropuje podle DB reality
- DLQ je explicitni stav, ne "tichy konec"

Doporuceni:

- zachovat pravidlo `DB first, queue second`
- u vsech novych async flow mit stejny kontrakt jako analysis lane
- kazdy job musi umet bezpecne opakovane spusteni
- kazdy side effect musi jit znovu odvodit z DB pri restartu

## 10. Observabilita orchestrace

Pro orchestrace doporucuji standardizovat 5 pohledu:

### A. Business flow metrics

- pocet case transitions podle typu
- doba `intake -> proposal_ready`
- doba `proposal_ready -> sent`
- pocet navratu do `draft`

### B. Queue metrics

- depth per lane
- processing count
- retry count
- DLQ count
- stale lease recovery count

### C. Case-level activity log

- timeline udalosti na zakazce
- kdo spustil command
- ktery job byl zalozen
- jaky export vznikl

### D. Failure classification

- provider timeout
- invalid payload
- catalog validation
- pricing unavailable
- export generation failed

### E. Operator-facing blockers

- proc nejde vytvorit final proposal
- proc nejde odeslat quote
- proc je case locked

To posledni uz dnes dobre smeruje pres `workflowStatus.blockingReasons`.

## 11. Doporucena implementacni struktura

Aby se orchestrace neroztekla po kodu, doporucuji tento ownership:

- `routes/`:
  request validation, auth, response contract
- `case_workflow/`:
  status commands a jejich effect registry
- `services/analysis_service.py`:
  analysis + quote follow-up orchestrace
- `services/project_service.py`:
  case aggregate detail + workflow projection
- `services/proposal_draft_service.py`:
  draft assembly
- `services/export_service.py`:
  export orchestrace
- `worker/`:
  transport, retry, lease, reconciliation
- `schemas/case_activity.py`:
  realtime event contract

Kdyz vznikne nova orchestracni logika, mela by mit jednoho vlastnika. Nemela by byt napul v route, napul ve view modelu a napul v websocket handleru.

## 12. Co doporucuji dodelat jako dalsi krok

### Faze 1 - sjednoceni orchestrace

- formalizovat seznam commandu nad zakazkou
- dopsat explicitni orchestration pravidla pro `analyzing -> proposal_ready`
- dopsat explicitni orchestration pravidla pro manualni korekce -> `quote_recalculation`
- sjednotit websocket event taxonomy

### Faze 2 - odolnost

- doplnit projection event sequence per case
- zmerit end-to-end latency po workflow krocich
- doplnit admin pohled na stuck cases a stalled async flow

### Faze 3 - obchodni workflow

- oddelit `proposal_ready` od `quote_ready` jeste vic na urovni snapshotu
- pridat email sending jako samostatny side effect po exportu
- pridat resumable orchestrace pro bulk operace a re-export

## 13. Strucne rozhodnuti

Doporuceny orchestration styl pro NOVU Builder je:

- `command-driven`
- `DB-authoritative`
- `event-assisted`
- `queue-backed`
- `realtime-projected`

Jinymi slovy:

Backend rozhodne, DB potvrdi, queue zpracuje, websocket promitne.

Tohle odpovida tomu, jak je repozitar postaven dnes, a zaroven to dava cistou cestu pro dalsi rust bez prepisu zakladnich modulu.
