# Orchestration Dispatch Allowlist

Tento seznam je zamerne explicitni.
Kodovy source of truth je:

- `python-backend/app/case_orchestration/orchestration_dispatch_registry.py`

Tento markdown je lidsky citelne zrcadlo registry a je hlidany testem proti driftu.

Cil:

- pojmenovat kazdy povoleny dispatch bod pro async transport
- rozlisit, co je jeste `infrastructure-only`
- rozlisit, co uz je `orchestration-owned`
- vse ostatni postupne zavirat do modelu:
  `Command -> Rule -> after_commit_jobs`

## Dispatch Registry

- `worker.enqueue_job`
  Low-level queue transport used by reconciliation and transport infrastructure.
- `analysis.enqueue`
  Analysis job dispatch triggered by orchestration or its sanctioned adapters.
- `quote.enqueue`
  Quote recalculation dispatch via command-driven orchestration path.
- `export.enqueue`
  Export generation dispatch via orchestration-owned flow.

## Infrastructure-Only

Tyto body jsou povolene jako technicka vrstva transportu nebo worker runtime.
Nemaji byt business autoritou pro workflow stav.

- `python-backend/app/worker/queue.py`
  definice analysis queue transport API
- `python-backend/app/worker/heavy_queue.py`
  definice heavy queue transport API
- `python-backend/app/worker/runner.py`
  worker startup reconciliation a retry transport
  povoleny dispatch: `worker.enqueue_job`
- `python-backend/app/services/photo_service.py`
  technicky dispatch pro photo/heavy processing
  povoleny dispatch: `worker.enqueue_job`

## Orchestration-Owned

Tyto body jsou povolene jen proto, ze dnes predstavuji orchestration boundary nebo jeji adapter.
Cilovy stav je drzet je pod table-driven command/rule modelem.

- `python-backend/app/case_workflow/action_effects.py`
  after-commit dispatch pro legacy case workflow actions
  povolene dispatch body: `analysis.enqueue`, `export.enqueue`
- `python-backend/app/services/analysis_service.py`
  analysis/quote follow-up adapter, uz napojeny na command path pro quote recalculation
  povolene dispatch body: `analysis.enqueue`, `quote.enqueue`, `worker.enqueue_job`
- `python-backend/app/services/export_service.py`
  export generation adapter
  povoleny dispatch: `export.enqueue`

## Zakazane Mimo Allowlist

Mimo tento seznam nesmi existovat prime:

- `enqueue_analysis_job(...)`
- `enqueue_heavy_job(...)`
- direct pricing trigger mimo `REQUEST_QUOTE_RECALCULATION`
- direct case status mutation

## Dalsi Uzaver

Prakticke dalsi kroky:

1. zmensovat `orchestration-owned` sekci
2. presouvat dispatch rozhodnuti z helperu/sluzeb do `RULES`
3. nechat `infrastructure-only` jen jako hloupe transport adaptery
