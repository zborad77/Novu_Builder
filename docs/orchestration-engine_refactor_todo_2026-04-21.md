# Orchestration Engine Refactor TODO

Tento TODO list pokryva 3 kriticke mezery odhalene rychlym auditem:

1. pricing recalculation je dnes spustitelny bokem pres HTTP route
2. deduplikace analysis/quote jobu neni tvrde vynucena DB
3. workflow transition helper je stale mutation-centric misto decision-first modelu

## Cil refaktoru

Posunout runtime o bezpecny krok bliz k deterministickemu orchestration engine bez rozbiti stavajicich flow.

## Implementacni kroky

### 1. Transition planning jako mezikrok k orchestratoru

- zavest cisty transition plan / decision objekt
- oddelit:
  - validaci transition
  - pripravu history/audit zaznamu
  - aplikaci na ORM model
- zachovat zpetnou kompatibilitu pro stavajici volani

### 2. Quote recalculation pres command-like entry point

- odstranit prime `analysis_service.enqueue_quote_recalculation_job(...)` z HTTP route
- zavest jedno centralni vstupni misto pro `REQUEST_QUOTE_RECALCULATION`
- validovat povoleny stav case pred zalozenim async jobu
- vracet stejny API shape, ale pres autoritativni workflow vstup

### 3. DB-level dedup guard pro aktivni jobs

- pridat unikatni omezeni / partial unique index pro aktivni `analysis_jobs`
- pokryt minimalne kombinaci:
  - `project_id`
  - `job_type`
  - aktivni status (`queued`, `running`)
- doplnit graceful handling pri konfliktu

## Success criteria

- pricing route uz neobchazi centralni workflow vstup
- aktivni analysis/quote job nelze zdvojit race conditionem
- transition helper umi vratit decision/plan bez okamzite side-effect mutace
- stavajici API kontrakty zustanou stabilni nebo budou zmeneny jen minimalne a vedome

## Poznamka

Toto jeste neni finalni `CaseOrchestrator` z execution planu.
Je to bezpecny mezikrok, ktery:

- zmensi architektonicky dluh
- zavede pevnejsi guardrails
- pripravi kod na pozdejsi table-driven orchestrator
