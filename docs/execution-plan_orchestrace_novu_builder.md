# Execution Plan: Orchestrace NOVU Builder

## Cil

Prevest stavajici architekturu NOVU Builder do jednotne, odolne a dobre pozorovatelne orchestrace, ktera:

- drzi `PostgreSQL` jako autoritativni zdroj pravdy
- pouziva `Redis` jen jako transport pro async vykon
- sjednocuje case workflow, analysis jobs, quote recalculation, proposal flow a exporty
- zobrazuje citelny realtime stav do desktop/web klienta
- je obnovitelna po restartu workeru a provoznich vypadcich

Tento plan navazuje na dokument [navrh-orchestrace_novu_builder.md](/d:/Novu_Hub/Novu_Builder/docs/navrh-orchestrace_novu_builder.md), ale zprisnuje ho do jednoho ciloveho execution modelu.

## Cilovy Execution Model

### 1. Jediny orchestration entry point

Cilovy backend model je:

```python
CaseOrchestrator.handle(command)
```

Ale zaroven plati jeste tvrdsi pravidlo:

- orchestrator rozhoduje
- orchestrator nepersistuje
- orchestrator neenqueueuje
- orchestrator neemituje eventy

Orchestrator je cisty decision engine.

Nic jineho nesmi primo menit:

- `case.status`
- workflow flags
- blocking reasons

To znamena:

- route handler nesmi menit case stav
- service mimo orchestrator nesmi menit case stav
- worker completion callback nesmi delat "implicitni transition"
- websocket vrstva je pouze projekce, nikdy ne autorita

### 2. Tvrdy command kontrakt v kodu

Textovy seznam nestaci. Cilem je zavadet command contract jako kodovy artefakt:

```python
class CaseCommand(Enum):
    SUBMIT_CASE = "submit_case"
    START_ANALYSIS = "start_analysis"
    ANALYSIS_COMPLETED = "analysis_completed"
    REQUEST_QUOTE_RECALCULATION = "request_quote_recalculation"
    QUOTE_RECALCULATED = "quote_recalculated"
    APPROVE_PROPOSAL = "approve_proposal"
    SEND_QUOTE = "send_quote"
    ARCHIVE_CASE = "archive_case"
```

System events jsou commands taky.

To je zasadni rozdil proti mekcimu planu:

- neni "system event bokem"
- neni "follow-up transition nekde v service"
- neni "implicitni side effect, ktery meni stav"

Pokud system dokonci analyzu, neposila "jen signal".
Posila command:

- `ANALYSIS_COMPLETED`

Pokud system dokonci pricing prepocet, neposila "jen update".
Posila command:

- `QUOTE_RECALCULATED`

### 3. Deterministicky state machine

Stavova logika nesmi byt rozeseta po codebase v `if` blocich.
Cil je jeden centralni transition registry, ktery validuje, co je v danem stavu dovoleno.

Minimalni cilovy backbone:

```python
TRANSITIONS = {
    "draft": ["SUBMIT_CASE"],
    "intake": ["START_ANALYSIS"],
    "analyzing": ["ANALYSIS_COMPLETED"],
    "proposal_pending": ["QUOTE_RECALCULATED"],
    "proposal_ready": ["APPROVE_PROPOSAL", "REQUEST_QUOTE_RECALCULATION"],
    "proposal_approved": ["SEND_QUOTE", "REQUEST_QUOTE_RECALCULATION"],
    "sent": ["ARCHIVE_CASE"],
}
```

Kazdy command:

1. validuje, ze je v danem stavu povoleny
2. jinak `FAIL CLOSED`
3. teprve potom vytvori side effecty

### 3.1 Table-Driven Orchestration

Tohle je kriticke pravidlo implementace:

- nestaci mit canonical matrix v dokumentu
- musi existovat i jako jediny zdroj pravdy v kodu

Zakazany vzor:

```python
if command == START_ANALYSIS:
    ...
elif command == ANALYSIS_COMPLETED:
    ...
```

Povoleny vzor:

```python
RULES = {
    ("intake", "START_ANALYSIS"): Rule(
        next_state="analyzing",
        before_commit=[CreateAnalysisJob()],
        after_commit=[EnqueueAnalysis()],
        events=[AnalysisStarted()],
    ),
    ("analyzing", "ANALYSIS_COMPLETED"): Rule(
        next_state="proposal_pending",
        before_commit=[CreateQuoteRecalc()],
        after_commit=[EnqueueQuote()],
        events=[AnalysisCompleted()],
    ),
}
```

Orchestrator pak ma byt trivialni:

```python
def handle(state, command):
    rule = RULES.get((state, command))
    if not rule:
        raise InvalidTransition()

    return CommandResult(...)
```

Tohle je zasadni, protoze:

- zadna rozlezla logika = zadne divergence
- determinismus je 100 procent vynutitelny
- audit architektury je diff tabulky, ne diff skrytych `if` vetvi
- fail-closed pravidlo je prirozene vychozi

### 4. Bez implicitnich transitions

Nesmi existovat zadna transition, ktera se "stane sama" mimo orchestrator.

Zakazane vzory:

- worker zmeni `case.status` primo v service
- route handler podle vysledku neceho "jen prepne status"
- websocket handler odvozuje stav a nekam ho zapisuje
- `proposal_ready` vznikne jako vedlejsi efekt bez commandu

Povoleny vzor:

1. system nebo user vytvori command
2. `CaseOrchestrator.handle(command)` rozhodne
3. DB se zmeni autoritativne
4. po commitu se enqueueuji side effecty

### 4.1 Zakazana business ownership mimo orchestrator

Tohle musi byt explicitne zakazane:

- `analysis_service` meni `case.status`
- `export_service` meni workflow stav
- `project_service` obsahuje business transition logiku

Tyto moduly mohou:

- cist data
- pripravovat payloady
- provadet specializovanou domenovou operaci
- vracet projection data

Tyto moduly nesmi:

- rozhodovat o dalsim case state
- menit workflow flags jako autorita
- menit blocking reasons jako autorita
- provadet transition bokem mimo `CaseOrchestrator.handle(...)`

Jedina povolena autorita pro workflow rozhodnuti je:

- `CaseOrchestrator.handle(...)`

### 5. Fail Closed

Defaultni chovani neni "nejak to projde".
Defaultni chovani je odmitnout command, pokud neni explicitne povoleny.

To plati pro:

- neznamy command
- command v nepovolenem stavu
- command bez povinnych dat
- command bez tenant scope
- command, ktery obchazi orchestrator

### 5.1 Impossible States Guards

Vedle transition validace doporucuji zavest i runtime guardy na nemozne stavy aggregate/projection vrstvy.

Referencni vzor:

```python
assert not (
    case.status == "proposal_ready"
    and not quote_snapshot_exists(case)
)
```

Tohle je posledni obranna vrstva proti tichym nekonzistencim:

- command nebo service sice nekde projde
- ale aggregate se dostane do stavu, ktery nema existovat

Minimalni pravidlo:

- `proposal_ready` nesmi existovat bez quote snapshotu / quote projection dat

Doporuceni:

- impossible-state guardy drzet blizko aggregate/projection boundary
- fail loud, ne tiše tolerovat rozbity stav
- postupne pridavat dalsi podobne invarianty podle kritickych workflow bodu

### 6. Side-Effect Pipeline jako kriticky invariant

Kazdy side effect musi jit pres presne 3 faze:

### A. BEFORE COMMIT

Tady vznika autoritativni zaznam v DB.

Typicky:

- `AnalysisJob`
- `QuoteRecalcRequest`
- `ExportJob`

Tohle je jedine misto, kde se side effect "rozhodne" a zapise.

### B. COMMIT

`DB commit` je jediny moment pravdy.

Dokud transaction neni commitnuta:

- side effect neni platny
- nic se nesmi enqueueovat
- nic se nesmi publikovat jako vykonany job

### C. AFTER COMMIT

Tady se dela pouze transport:

- enqueue do Redis
- pripadne publish projection eventu

Transport nikdy nesmi predbehnout DB autoritu.

Referencni vzor:

```python
result = orchestrator.handle(command)

with db.transaction():
    persist(result.before_commit_records)
    update_case_state(result.next_state)

after_commit():
    enqueue(result.after_commit_jobs)
    emit_events(result.emitted_events)
```

Zakazane vzory:

- enqueue pred commitem
- side effect bez DB zaznamu
- transport, ktery neodpovida autoritativnimu DB rozhodnuti
- orchestrator, ktery sam provadi side effecty

### 7. Klicova orchestration osa

Nejdolezitejsi cast systemu je analysis flow.
Ten musi byt 100 procent deterministicky a musi existovat jen jedna povolena osa:

```text
START_ANALYSIS
    ->
AnalysisJob created
    ->
worker
    ->
ANALYSIS_COMPLETED (command)
    ->
QuoteRecalcRequest created
    ->
worker
    ->
QUOTE_RECALCULATED (command)
    ->
proposal_ready
```

Zakazane vzory:

- preskocit krok
- mit paralelni logiku pro pricing follow-up
- nechat UI triggerovat pricing jako autoritativni workflow krok
- prejit do `proposal_ready` bez `QUOTE_RECALCULATED`

To znamena:

- `START_ANALYSIS` vytvari autoritativni `AnalysisJob`
- worker nikdy neprepina case stav primo
- worker po dokonceni vytvori system command `ANALYSIS_COMPLETED`
- `ANALYSIS_COMPLETED` vytvori autoritativni `QuoteRecalcRequest`
- worker pro pricing nikdy neprepina case stav primo
- az `QUOTE_RECALCULATED` smi privest case do `proposal_ready`

### 8. Reconciliation je povinna soucast orchestrace

Bez reconciliation neni system recoverable.

Po restartu workeru musi system umet deterministicky obnovit nedokonceny tok:

```python
reconcile():
    find AnalysisJob where status = running -> requeue
    find QuoteRecalcRequest where status in ("pending", "running") -> requeue
    find ExportJob where status in ("pending", "running", "stuck") -> retry
```

Minimalni pravidla:

- DB je autorita pro rozhodnuti, co je stale aktivni
- Redis transport se muze ztratit, DB stav se nesmi ztratit
- reconciliation musi existovat pro analysis, quote recalculation i exporty
- startup bez reconciliation neni povolen v strict runtime modu

Bez toho:

- system neni recoverable
- orchestrace je iluze

### 9. Realtime je pouze projekce DB state change

Realtime event nikdy nesmi vzniknout primo z:

- UI
- workeru bez DB state change

Realtime event smi vzniknout pouze z:

- `DB state change -> event emitter`

To znamena:

- UI muze poslat command, ale negeneruje autoritativni event
- worker muze dokoncit job, ale event vznika az po DB zmene
- websocket stream je jen projekce potvrzeneho backend stavu

### 10. Operatorsky model je povinna soucast orchestrace

Provoz orchestrace musi mit 3 samostatne pohledy:

### 1. CASE TIMELINE

Timeline jednoho case:

- `draft -> intake -> analyzing -> proposal_ready -> ...`
- command history
- emitted events
- blocking reasons
- audit/context metadata

Tento pohled odpovida na otazku:

- co se na case stalo a v jakem poradi

### 2. JOB VIEW

Operacni pohled na async vykon:

- analysis jobs
- quote jobs
- export jobs

Minimalne pro kazdy job typ:

- status
- created_at
- started_at
- finished_at
- retry_count / attempt_count
- caused_by_case_id
- caused_by_command

Tento pohled odpovida na otazku:

- ktera konkretni async uloha je problem

### 3. STUCK DETECTOR

Detekce orchestration stuck stavu:

- `analyzing > X min`
- `proposal_pending` bez quote completion
- `export pending > X`

Tento pohled odpovida na otazku:

- kde je system zaseknuty a potrebuje zasah nebo retry

### 11. Anti-Patterny, ktere rozbiji system

Pokud se objevi tyto vzory, orchestrace se postupne rozpadne.

### 1. Service-level orchestrace

Zakazany vzor:

```python
analysis_service.do_everything()
```

To znamena:

- jedna service sama rozhoduje o workflow
- sama vytvari side effecty
- sama prepina case state
- sama supluje orchestrator

Duledek:

- ztrata centralni autority
- skryte transitions
- netestovatelny flow ownership

### 2. UI triggeruje business flow

Zakazany vzor:

```python
onClick -> call pricing + status update
```

To znamena:

- UI spousti pricing jako business autoritu
- UI rozhoduje o workflow state
- klient obchazi command model

Duledek:

- nekonzistentni backend stav
- duplicity flow
- zavislost business logiky na klientovi

### 3. Worker meni stav bez commandu

Zakazany vzor:

```python
case.status = "proposal_ready"
```

To znamena:

- worker zapisuje finalni workflow stav primo
- chybi command envelope
- chybi centralni transition validace

Duledek:

- implicitni transitions
- poruseni fail-closed modelu
- rozpad auditovatelnosti

### 4. Event jako source of truth

Zakazany vzor:

```python
state = ws_event
```

To znamena:

- websocket event urcuje autoritativni stav
- klient veri streamu vic nez DB projekci
- event nahrazuje aggregate snapshot

Duledek:

- drift mezi streamem a DB
- race conditions pri reconnectu
- nekonzistentni optimistic concurrency

### Pravidlo preziti

Proti vsem temto anti-patternum plati jediny proti-model:

- command vstupuje pres `CaseOrchestrator.handle(...)`
- DB je autorita
- worker provadi vykon, ne workflow rozhodnuti
- event je projekce, ne source of truth

## Canonical Runtime Shape

Doporuceny cilovy tvar backendu:

```python
class CaseState(Enum):
    DRAFT = "draft"
    INTAKE = "intake"
    ANALYZING = "analyzing"
    PROPOSAL_PENDING = "proposal_pending"
    PROPOSAL_READY = "proposal_ready"
    PROPOSAL_APPROVED = "proposal_approved"
    SENT = "sent"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class CaseCommandEnvelope:
    case_id: str
    command: CaseCommand
    actor_user_id: str | None
    organization_id: str | None
    payload: dict[str, object]
    correlation_id: str
    caused_by_job_id: str | None = None
```

```python
class CaseOrchestrator:
    async def handle(self, envelope: CaseCommandEnvelope) -> CommandResult:
        ...
```

Vedle toho musi existovat table-driven registry:

```python
@dataclass(frozen=True)
class Rule:
    next_state: str
    before_commit: list[DBRecordSpec]
    after_commit: list[JobSpec]
    events: list[EventSpec]


RULES: dict[tuple[str, str], Rule]
```

`CommandResult` ma vratit minimalne:

- novy stav
- `before_commit_records`
- `after_commit_jobs`
- `emitted_events`

Tvrdy kontrakt:

- `CaseOrchestrator` nesmi delat side effecty
- `CaseOrchestrator` pouze vraci `CommandResult`
- persistence a transport vykonava az vnejsi execution pipeline

Cilovy tvar:

```python
@dataclass(frozen=True)
class CommandResult:
    next_state: str
    before_commit_records: list[DBRecord]
    after_commit_jobs: list[JobSpec]
    emitted_events: list[EventSpec]
```

Vedle toho doporucuji zavest explicitni model pro side-effect plan:

```python
@dataclass(frozen=True)
class PlannedSideEffect:
    kind: str
    db_record_id: str
    transport_channel: str | None
    payload: dict[str, object]
```

`CommandResult` pak nema vracet "jen co se stalo", ale i:

- co bylo autoritativne zalozeno v DB
- co ma byt po commitu transportovano

## Canonical Execution Pipeline

Toto je jediny povoleny vykonovy model kolem orchestratoru:

```python
result = orchestrator.handle(command)

with db.transaction():
    persist(result.before_commit_records)
    update_case_state(result.next_state)

after_commit():
    enqueue(result.after_commit_jobs)
    emit_events(result.emitted_events)
```

Timhle modelem:

- eliminujes side-effect leak
- mas plnou kontrolu nad poradim
- testovatelnost dramaticky roste

Tvrdy invariant:

- orchestrator nesmi delat side effecty
- orchestrator nesmi sam sahat do Redis
- orchestrator nesmi sam emitovat eventy
- orchestrator nesmi sam commitovat DB transaction

Pro realtime projection doporucuji cilovy envelope:

```python
@dataclass(frozen=True)
class CaseProjectionEvent:
    event_id: str
    case_id: str
    sequence: int
    version: int
    event_type: str
    payload: dict[str, object]
```

Kriticke invarianty:

- `sequence` = ordering eventu v ramci case
- `version` = optimistic concurrency pro klienta
- event se publikuje az po autoritativni DB zmene

## Canonical Command Matrix

Tohle je cilovy implementacni kontrakt pro orchestrator.

| Command                       | Allowed state                         | BEFORE COMMIT record                                | Next state          | AFTER COMMIT transport             | Emitted event                                      | Forbidden shortcut                                 |
| ----------------------------- | ------------------------------------- | --------------------------------------------------- | ------------------- | ---------------------------------- | -------------------------------------------------- | -------------------------------------------------- |
| `SUBMIT_CASE`                 | `draft`                               | audit/history row                                   | `intake`            | none                               | `case_transition_applied`                          | route nesmi prepnout `draft -> intake` primo       |
| `START_ANALYSIS`              | `intake`                              | `AnalysisJob`                                       | `analyzing`         | enqueue `analysis` lane            | `analysis_job_queued`                              | zadny enqueue bez `AnalysisJob`                    |
| `ANALYSIS_COMPLETED`          | `analyzing`                           | `AnalysisResult` + `QuoteRecalcRequest`             | `proposal_pending`  | enqueue quote recalculation worker | `analysis_completed`, `quote_recalculation_queued` | worker nesmi prepnout rovnou do `proposal_ready`   |
| `REQUEST_QUOTE_RECALCULATION` | `proposal_ready`, `proposal_approved` | `QuoteRecalcRequest`                                | `proposal_pending`  | enqueue quote recalculation worker | `quote_recalculation_queued`                       | UI nesmi pricing spoustet bokem mimo command       |
| `QUOTE_RECALCULATED`          | `proposal_pending`                    | recalculated quote snapshot / proposal draft update | `proposal_ready`    | none                               | `quote_recalculated`                               | pricing worker nesmi menit stav primo              |
| `APPROVE_PROPOSAL`            | `proposal_ready`                      | approval snapshot / lock record                     | `proposal_approved` | none                               | `case_transition_applied`                          | approval nesmi vzniknout jako UI-local flag        |
| `SEND_QUOTE`                  | `proposal_approved`                   | `ExportJob`                                         | `sent`              | enqueue `export_generate`          | `export_queued`, `case_transition_applied`         | export enqueue bez `ExportJob` je zakazany         |
| `ARCHIVE_CASE`                | `sent`                                | `ExportJob`                                         | `archived`          | enqueue `export_generate`          | `export_queued`, `case_transition_applied`         | archivace nesmi probihat bokem pres service update |

Poznamky k matici:

- `REQUEST_QUOTE_RECALCULATION` je jediny povoleny zpusob, jak vratit case z `proposal_ready` nebo `proposal_approved` zpet do `proposal_pending`
- `APPROVE_PROPOSAL` je oddeleny krok; `SEND_QUOTE` nesmi byt povoleno z `proposal_ready`
- command muze vytvorit vice autoritativnich DB zaznamu, ale zadny transport nesmi probehnout pred commitem
- event emitter cte z autoritativni DB zmeny, ne z UI ani z worker callbacku

## Executive Summary

Doporuceny postup je rozdelit realizaci do 5 fazi:

1. zavest orchestration kernel v kodu
2. migrovat vsechny case transitions za `CaseOrchestrator`
3. napojit analysis, quote a export flow jako system commands
4. sjednotit projection a realtime stream
5. dopsat observabilitu, recovery a release gate

Priorita neni pridavat dalsi features, ale zpevnit hlavni tok:

`draft -> intake -> analyzing -> proposal_pending -> proposal_ready -> proposal_approved -> sent -> archived`

## Scope

V tomto execution planu je zahrnuto:

- `CaseOrchestrator` jako jediny entry point
- `CaseCommand` a `CaseState` contract v kodu
- centralni `TRANSITIONS` registry
- analysis lane a heavy lane orchestrace
- system commands pro analysis a pricing follow-up
- websocket activity projekce
- observabilita a recovery guardrails

Mimo scope prve vlny:

- nova AI feature logika
- redesign klienta
- nove CRM moduly
- billing nebo invoicing
- rozsahle produktove rozsireni mimo hlavni case flow

## Faze 0: Orchestration Kernel

### Cil

Vytvorit tvrdy execution kernel, kolem ktereho se bude migrovat zbytek backendu.

### Deliverables

- `CaseCommand` enum
- `CaseState` enum
- `CaseCommandEnvelope`
- `CaseOrchestrator.handle(command)`
- `CommandResult` jako jediny vystup orchestratoru
- `RULES[(state, command)] -> Rule` registry
- centralni `TRANSITIONS`
- jednotna chyba typu `InvalidCaseTransitionError` nebo ekvivalent
- side-effect plan model pro `before_commit` vs `after_commit`

### Konkretni ukoly

- zalozit modul typu `python-backend/app/case_orchestration/`
- zavadet:
  - `commands.py`
  - `states.py`
  - `transitions.py`
  - `orchestrator.py`
  - `results.py`
  - `side_effects.py`
- definovat explicitni mapu user a system commandu
- definovat fail-closed validator pro command vs state
- definovat command envelope s actor a correlation metadata
- zavest table-driven registry:
  - `RULES[(state, command)] -> Rule`
- zajistit, ze orchestrator pouze:
  - nacte rule
  - validuje existenci rule
  - vrati `CommandResult`
- definovat API mezi:
  - orchestrator handle
  - DB persistence
  - after-commit transport dispatch
- oddelit:
  - decision phase (`CommandResult`)
  - persistence phase
  - after-commit transport phase

### Acceptance Criteria

- existuje jeden kodovy command contract
- existuje jedna centralni transition mapa
- existuje jeden orchestrator entry point
- `CommandResult` je jediny povoleny vystup orchestratoru
- `RULES` registry je jediny zdroj pravdy pro `(state, command) -> rule`
- command mimo transition mapu je odmitnut
- side effect je vzdy rozdelen na `BEFORE COMMIT -> COMMIT -> AFTER COMMIT`
- orchestrator sam neprovadi persistence, enqueue ani event emission
- orchestrator neobsahuje rozlezle `if/elif` vetveni podle commandu

### Odhad

- 1 az 2 dny

## Faze 1: Migrace Case Status Ownership

### Cil

Presunout ownership nad `case.status`, workflow flags a blocking reasons pod orchestrator.

### Deliverables

- route handlery uz priamo nemeni stav case
- worker callbacky uz priamo nemeni stav case
- `CaseActionService` nebo ekvivalent je napojen na orchestrator
- projection vrstva cte uz jen autoritativni vysledky orchestrace

### Konkretni ukoly

- projit route handlery a najit vsechny prime zmeny `project.status`
- projit service metody, ktere delaji side-effect transition bez commandu
- projit worker completion flow a odstranit prime state mutation
- napojit stavajici human actions na:
  - `SUBMIT_CASE`
  - `START_ANALYSIS`
  - `APPROVE_PROPOSAL`
  - `SEND_QUOTE`
  - `ARCHIVE_CASE`
- vyresit ownership pro workflow flags a blocking reasons:
  - bud jsou plne odvozene z case state
  - nebo jsou zapisovany jen orchestrator projection krokem

### Implementacni poznamky

- `before_commit` vytvari autoritativni zaznamy typu `AnalysisJob` nebo `ProjectExport`
- `after_commit` pouze enqueueuje transport do Redis
- nic mimo orchestrator nesmi umet "jen prepnout case"
- nesmi existovat enqueue pred commitem
- nesmi existovat side effect bez DB zaznamu

### Acceptance Criteria

- neexistuje prime nastavovani `case.status` mimo orchestrator
- workflow flags nejsou rozsypane po service vrstvach
- blocking reasons vznikaji deterministicky z orchestrator/projection logiky
- side effect pipeline je vsude `DB first, transport second`
- `analysis_service`, `export_service` ani `project_service` neobsahuji autoritativni workflow transition rozhodnuti
- neexistuje service-level orchestrace typu `analysis_service.do_everything()`

### Rizika

- cast logiky muze byt stale schovana v `AnalysisService` nebo `ProjectService`
- dnesni `case_workflow` registr uz muze byt polovicni orchestrator a polovicni transition helper

### Odhad

- 2 az 4 dny

## Faze 2: System Commands pro Analysis a Quote Flow

### Cil

Udelat z analysis a pricing nasledku explicitni system-command pipeline.

### Deliverables

- `ANALYSIS_COMPLETED` jako system command
- `REQUEST_QUOTE_RECALCULATION` jako explicitni command
- `QUOTE_RECALCULATED` jako system command
- zavedeny stav `proposal_pending` mezi analyze a finalnim proposal ready
- `REQUEST_QUOTE_RECALCULATION` jako jediny navrat z ready/approved zpet do pricing pipeline

### Konkretni ukoly

- po dokonceni analysis jobu nevykonavat transition primo
- misto toho vytvorit a odbavit:
  - `ANALYSIS_COMPLETED`
- `ANALYSIS_COMPLETED` musi:
  - validovat stav `analyzing`
  - ulozit analysis vysledek
  - vytvorit side effect `REQUEST_QUOTE_RECALCULATION`
  - prepnout case do `proposal_pending`, pokud je to cilovy model
- po dokonceni pricing prepocitu nevykonavat transition primo
- misto toho vytvorit a odbavit:
  - `QUOTE_RECALCULATED`
- `QUOTE_RECALCULATED` musi:
  - validovat stav `proposal_pending`
  - potvrdit pripravenost proposal dat
  - prepnout case do `proposal_ready`
- `REQUEST_QUOTE_RECALCULATION` musi:
  - byt povolen pouze z `proposal_ready` nebo `proposal_approved`
  - vytvorit autoritativni `QuoteRecalcRequest`
  - vratit case do `proposal_pending`
- odstranit vsechny alternativni pricing follow-up cesty mimo tuto osu:
  - analyze -> direct proposal ready
  - UI -> direct pricing trigger jako autoritativni transition
  - service-internal implicit pricing transition

### Implementacni poznamky

- system events jsou command envelopes se `actor_user_id=None`
- `caused_by_job_id` ma byt vyplnen pro traceability
- pokud manualni korekce meni pricing podklady, musi jit pres:
  - `REQUEST_QUOTE_RECALCULATION`
- `ANALYSIS_COMPLETED` nesmi enqueueovat pricing follow-up bez autoritativniho DB zaznamu `QuoteRecalcRequest`

### Acceptance Criteria

- po analyze nevznika zadna implicitni transition
- quote recalculation je first-class command flow
- `proposal_ready` se objevi jen pres `QUOTE_RECALCULATED`
- navrat do pricing pipeline jde pouze pres `REQUEST_QUOTE_RECALCULATION`
- command v nespravnem stavu failne closed
- neexistuje pricing enqueue bez predchoziho DB request zaznamu
- analysis flow je jedina povolena orchestration osa pro vznik `proposal_ready`

### Rizika

- dnesni kod muze mit follow-up pricing logic tesne navazanou uvnitr `AnalysisService.execute_job`
- zavedenim `proposal_pending` muze byt potreba upravit projection a klienta

### Odhad

- 3 az 5 dnu

## Faze 3: Send / Archive jako plne orchestrated flow

### Cil

Stejny model dotahnout i do export a completion vetve.

### Deliverables

- `APPROVE_PROPOSAL` jako jediny command pro schvaleni navrhu
- `SEND_QUOTE` jako jediny command pro odeslani
- `ARCHIVE_CASE` jako jediny command pro archivaci
- exporty vytvarene jako side effect orchestrace

### Konkretni ukoly

- zajistit, ze `APPROVE_PROPOSAL`:
  - validuje stav `proposal_ready`
  - vytvari approval snapshot nebo lock record
  - meni case do `proposal_approved`
- zajistit, ze `SEND_QUOTE`:
  - validuje stav `proposal_approved`
  - zaklada autoritativni `ExportJob`
  - meni case do `sent`
  - po commitu enqueueuje `export_generate`
- zajistit, ze `ARCHIVE_CASE`:
  - validuje stav `sent`
  - zaklada autoritativni `ExportJob`
  - meni case do `archived`
  - po commitu enqueueuje `export_generate`

### Acceptance Criteria

- `approve proposal` flow nema zadny bokem skryty status update
- `send` flow nema zadny bokem skryty status update
- `archive` flow nema zadny bokem skryty status update
- export je vzdy side effect po commandu, ne duvod state mutation mimo orchestrator
- neexistuje export enqueue bez predchoziho DB `ExportJob` zaznamu

### Rizika

- dnesni model muze mit cast approval semantics stale skrytou v UI nebo draft service
- bude potreba srovnat stare `quote_ready` pojmenovani s novym `proposal_approved`

### Odhad

- 2 az 3 dny

## Faze 4: Projection a Realtime Model

### Cil

Napojit websocket a detail case na autoritativni command-driven stav.

### Deliverables

- jednotny event envelope pro `case_activity_ws`
- projection vrstva navazana na orchestrator result
- konzistentni `workflowStatus` a `blockingReasons`
- event emitter navazany pouze na DB state change
- operatorsky `CASE TIMELINE` projection

### Konkretni ukoly

- zavest jednotny event shape:
  - `eventId`
  - `caseId`
  - `eventType`
  - `occurredAt`
  - `sequence`
  - `version`
  - `payload`
- eventy publikovat z command result nebo navazne projection vrstvy
- definovat minimalni event taxonomy:
  - `case_command_accepted`
  - `case_transition_applied`
  - `analysis_job_queued`
  - `analysis_completed`
  - `quote_recalculation_queued`
  - `quote_recalculated`
  - `export_queued`
  - `export_completed`
- rozhodnout, co je pure projection a co je refetch trigger
- navrhnout timeline aggregate pro case:
  - transitions
  - commands
  - emitted events
  - blocking reasons

### Implementacni poznamky

- websocket nesmi byt source of truth
- event sequence musi byt monotoni v ramci case
- `version` musi rust s autoritativni zmenou case aggregate
- `blockingReasons` ma byt citelna projekce autoritativniho stavu, ne ruce psany chaos z vice mist
- event nesmi vzniknout primo z UI ani primo z workeru bez DB state change

### Acceptance Criteria

- desktop/web klient dostava konzistentni eventy pro hlavni workflow
- websocket event jde vzdy od command result nebo autoritativni state zmeny
- reconnect nevede k rozbitemu lokalnimu stavu
- klient muze pouzit `version` pro optimistic concurrency guard
- existuje operator-friendly `CASE TIMELINE` pohled nad jednim case

### Rizika

- dnesni websocket kontrakt muze byt napojen na konkretni Qt klient
- projection muze stale tahat data z vice service mist bez centralniho ownership

### Odhad

- 2 az 4 dny

## Faze 5: Recovery, Observabilita a Release Gate

### Cil

Udelat z orchestrace releaseable subsystem, ne jen implementacni refactor.

### Deliverables

- test matrix pro command/state contract
- integration testy pro side effect enqueue semantics
- recovery rehearsal scenare
- release gate pro orchestration subsystem
- startup reconciliation pro vsechny tri job typy
- orchestration invariant test suite
- operatorsky `JOB VIEW`
- operatorsky `STUCK DETECTOR`

### Konkretni ukoly

- doplnit samostatnou kategorii testu:
  - `ORCHESTRATION INVARIANT TESTS`
- doplnit testy pro:
  - invalid command in state -> fail closed
  - valid command -> deterministic transition
  - `ANALYSIS_COMPLETED` -> `REQUEST_QUOTE_RECALCULATION`
  - `QUOTE_RECALCULATED` -> `proposal_ready`
  - `SEND_QUOTE` -> `export_generate`
  - enqueue se nespusti pri rollbacku transaction
  - side effect bez DB zaznamu je odmitnut
  - startup reconcile vraci `AnalysisJob(status=running)` zpet do vykonu
  - startup reconcile vraci `QuoteRecalcRequest(status=pending|running)` zpet do vykonu
  - startup reconcile vraci stuck `ExportJob` do retry flow
  - startup reconciliation po restartu workeru
  - websocket initial snapshot + update stream
- doplnit invariant testy minimalne pro:
  - `test_no_state_skip()`
  - `test_analysis_always_triggers_quote()`
  - `test_no_double_jobs()`
  - `test_proposal_ready_requires_quote_snapshot()`
  - `test_worker_cannot_set_case_state_directly()`
  - `test_ui_cannot_be_source_of_business_transition()`
  - `test_event_is_not_source_of_truth()`
  - `test_every_allowed_transition_has_rule()`
  - `test_orchestrator_is_table_driven()`
- doplnit metrics:
  - command rejection count
  - state transition count
  - queue side effect count
  - recovery requeue count
- doplnit operatorske pohledy:
  - `CASE TIMELINE`
  - `JOB VIEW`
  - `STUCK DETECTOR`
- pro `JOB VIEW` zobrazit minimalne:
  - analysis jobs
  - quote jobs
  - export jobs
- pro `STUCK DETECTOR` zavest minimalne pravidla:
  - `analyzing > X min`
  - `proposal_pending` bez quote completion
  - `export pending > X`
- spustit rehearsal:
  - worker restart behem `running` jobu
  - Redis restart / ztrata transport state
  - duplicate system command delivery
  - restart mezi `ANALYSIS_COMPLETED` a enqueue quote recalculation transportu
  - restart mezi `SEND_QUOTE` a enqueue export transportu

### Acceptance Criteria

- command contract je automaticky testovany
- invalid transition nikdy "neprojde nahodou"
- hlavni recovery scenare jsou odzkousene
- release gate ma jasna meritelna pravidla
- je automaticky pokryto, ze enqueue nikdy nepredbiha commit
- reconciliation pokryva analysis, quote recalculation i export flow
- orchestration invariant testy chrani:
  - zakaz preskoceni stavu
  - povinny analysis -> quote follow-up
  - deduplikaci jobu
  - zakaz service-level orchestrace
  - zakaz worker direct state mutation
  - zakaz event-as-source-of-truth model
  - table-driven rule registry jako jediny decision source
- operator ma k dispozici 3 pohledy:
  - `CASE TIMELINE`
  - `JOB VIEW`
  - `STUCK DETECTOR`
- stuck detector umi odhalit minimalne:
  - `analyzing > X min`
  - `proposal_pending` bez quote
  - `export pending > X`

### Doporucene invariant testy

```python
def test_no_state_skip():
    assert not possible("analyzing", "sent")


def test_analysis_always_triggers_quote():
    assert quote_job_created_after_analysis()


def test_no_double_jobs():
    assert deduplication()


def test_proposal_ready_requires_quote_snapshot():
    assert impossible_state_is_rejected()


def test_worker_cannot_set_case_state_directly():
    assert worker_must_emit_command_not_mutate_state()


def test_ui_cannot_be_source_of_business_transition():
    assert ui_cannot_authoritatively_advance_workflow()


def test_event_is_not_source_of_truth():
    assert state_is_loaded_from_db_projection_not_ws_only()


def test_every_allowed_transition_has_rule():
    assert all_transition_pairs_are_covered_by_rules()


def test_orchestrator_is_table_driven():
    assert orchestrator_resolves_rule_not_branch_logic()
```

### Rizika

- bez duplicate-delivery testu nebude jasne, jak robustni jsou system commands
- bez fail-closed testu se model rychle rozpadne zpet do ad hoc logiky
- bez invariant testu se workflow casem znovu roztece do service vrstvy
- bez anti-pattern guardu se architektura vrati k service orchestration a klientske autorite

### Odhad

- 3 az 5 dnu

## Doporucene Poradi Implementace

Prakticke poradi bych drzel takto:

1. Faze 0
2. Faze 1
3. Faze 2
4. Faze 3
5. Faze 4
6. Faze 5

Nedoporucuji zacit websocketem, observabilitou ani UI integraci driv, nez bude hotovy orchestration kernel a ownership nad case stavem.

## Kriticka Cesta

Za critical path povazuji:

1. zavest `CaseOrchestrator.handle(command)`
2. zavest `CaseCommand` + `CaseState` + centralni `TRANSITIONS`
3. odstranit prime state mutation mimo orchestrator
4. prevest `ANALYSIS_COMPLETED` a `QUOTE_RECALCULATED` na system commands
5. prevest `SEND_QUOTE` a `ARCHIVE_CASE` na stejny model

Jestli se tato osa nerozbije, vse ostatni lze dodelavat iterativne.

## Zodpovednosti

Doporuceny ownership:

- orchestration kernel:
  `python-backend/app/case_orchestration/`
- integrace do stavajicich flow:
  `python-backend/app/case_workflow/`
  `python-backend/app/services/analysis_service.py`
  `python-backend/app/services/export_service.py`
- projection vrstva:
  `python-backend/app/services/project_service.py`
  websocket route
  schema kontrakty
- worker reliability:
  `python-backend/app/worker/queue.py`
  `python-backend/app/worker/heavy_queue.py`
  `python-backend/app/worker/runner.py`
- klientska integrace:
  Qt/Web jen jako konzumenti commandu a projection eventu

## Milestones

### M1: Kernel Ready

- `CaseCommand` existuje
- `CaseState` existuje
- `CaseOrchestrator.handle(command)` existuje
- `TRANSITIONS` je centralni a fail-closed

### M2: Ownership Ready

- `case.status` se nemeni mimo orchestrator
- workflow flags a blocking reasons maji jednoho ownera
- route ani worker neprovadi implicitni transition

### M3: System Commands Ready

- `ANALYSIS_COMPLETED` je command
- `REQUEST_QUOTE_RECALCULATION` je command
- `QUOTE_RECALCULATED` je command
- `proposal_ready` nevznika implicitne

### M3.5: Approval Flow Ready

- `APPROVE_PROPOSAL` je command
- `SEND_QUOTE` je povoleno az z `proposal_approved`
- approval neni lokalni UI flag

### M4: Projection Ready

- websocket ma jednotny envelope
- klient dostava konzistentni eventy
- reconnect + refetch flow je funkcni
- existuje `CASE TIMELINE` projection pro operatora

### M5: Release Ready

- testy a rehearsals jsou green
- duplicate delivery i invalid transition jsou pokryte
- release gate je formalne splnen
- operator ma `JOB VIEW` a `STUCK DETECTOR`

## Doplnujici Rozhodnuti

Pri realizaci doporucuji drzet tato rozhodnuti stabilne:

- system events jsou commands taky
- nepridavat implicitni transitions
- nedelat websocket z druhe business vrstvy
- nenechat klienta pocitat finalni obchodni stav
- nenechat UI triggerovat pricing jako autoritativni orchestration krok
- `CommandResult` je jediny vystup orchestratoru
- orchestrator je cisty decision engine
- `analysis_service` nesmi menit `case.status`
- `export_service` nesmi menit workflow stav
- `project_service` nesmi obsahovat autoritativni business transition logiku
- service-level orchestrace je zakazana
- table-driven orchestration je povinna
- UI nesmi triggerovat business flow jako autorita
- worker nesmi menit stav bez commandu
- event nesmi byt source of truth
- orchestrator nesmi delat side effecty
- nedovolit transition bez auditovatelneho command entry pointu
- nedovolit async side effect pred DB commitem
- nedovolit enqueue bez autoritativniho DB job zaznamu
- realtime event emitovat pouze z DB state change
- default je `fail closed`

## Ocekavany Vysledek

Po dokonceni tohoto execution planu bude NOVU Builder mit:

- jeden orchestration entry point
- jeden command contract v kodu
- jeden deterministicky state machine model
- explicitni system commands misto skrytych transition
- realtime stream, ktery promita realny stav
- lepsi provozni diagnostiku a jednodussi recovery

To je pevnejsi a cistejsi model nez "command-driven architektura obecne". Je to konkretni execution kernel, kolem ktereho se da backend disciplinovane dostavet.
