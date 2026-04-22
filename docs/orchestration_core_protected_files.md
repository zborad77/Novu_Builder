# Orchestration Core Protected Files

Tyto soubory tvori aktualni orchestration kernel nebo jeho kriticke ochrany. Nesmí se menit lehce ani bokem v unrelated refactorech.

## Protected Files

Machine-readable source of truth pro tento seznam je:

- `.github/orchestration_protected_files.txt`

- `python-backend/app/case_orchestration/quote_recalculation.py`
  current command-driven RULES registry, fail-closed command handling, canonical side-effect plan pro quote recalculation

- `python-backend/app/case_orchestration/orchestration_dispatch_registry.py`
  single source of truth pro sanctioned dispatch body a allowed call sites

- `python-backend/app/case_orchestration/dispatch_guard.py`
  runtime fail-closed enforcement proti neregistrovanemu dispatch

- `python-backend/app/services/project_service.py`
  impossible-state guards, sequence-level invarianty a aggregate/projection boundary

- `python-backend/app/repositories/project_repository.py`
  aggregate load boundary pro invariants; musi nacitat stav potrebny pro assert_no_impossible_state

- `python-backend/app/worker/runner.py`
  startup reconciliation entry points pro analysis, exporty a heavy-lane recovery

- `python-backend/app/worker/queue.py`
  analysis lane transport contract a dispatch-guarded enqueue path

- `python-backend/app/worker/heavy_queue.py`
  heavy lane transport contract a dispatch-guarded enqueue path

## Change Policy

- zmena protected file vyzaduje rerun orchestration release gate
- zmena protected file musi mit explicitni duvod v PR / changelogu
- zmena protected file nesmi oslabit fail-closed nebo DB-first invariant bez aktualizace audit testu
- zmena protected file nesmi obchazet dispatch registry ani impossible-state guards

## Review Triggers

Zesilena review pozornost je povinna, pokud zmena saha na:

- `RULES`
- allowed dispatch names nebo sanctioned call sites
- startup reconciliation
- impossible-state guards
- enqueue semantics pred/po commitu

## Enforcement

- CI vzdy spousti orchestration release gate samostatnym jobem
- repo guard pri zmene protected file kontroluje PR checklist
- naschval zde neni slepe pridany `CODEOWNERS`, dokud nebude potvrzeny spravny seznam GitHub owneru
