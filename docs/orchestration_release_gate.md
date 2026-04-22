# Orchestration Release Gate

Tento gate zamyka orchestration core pred releasem. Pokud neni green, orchestration se nepovazuje za release-ready.

## Povinne sady

1. `invariant guards`
   `python-backend/tests/test_orchestration_invariant_guards.py`

2. `dispatch registry enforcement`
   `python-backend/tests/test_dispatch_registry_enforcement.py`

3. `rehearsal scenarios`
   `python-backend/tests/test_rehearsal_scenarios.py`

4. `critical flow integration`
   `python-backend/tests/test_quote_recalculation_command_orchestrator.py`
   `python-backend/tests/test_quote_recalculation_rules_coverage_audit.py`
   `python-backend/tests/test_estimates_recalculate_route.py`
   `python-backend/tests/test_quote_recalculation_jobs.py`
   `python-backend/tests/test_case_workflow_transition_planning.py`
   `python-backend/tests/test_case_transition_effects.py`

## Canonical Run Command

```powershell
python scripts/verify_orchestration_release_gate.py
```

CI log zaroven vypisuje i `Gate version`, aby byl gate auditovatelny pri zmenach a rollbacku.

## Gate Version Notes

`2026-04-22.1`

- initial enforced gate
- includes invariant guards
- includes dispatch registry enforcement
- includes rehearsal scenarios
- includes critical flow integration

## CI Enforcement

- GitHub CI ma samostatny job `orchestration-release-gate`
- zmena protected orchestration file musi mit green tento job pred mergem
- repo guard navic na PR kontroluje, ze je vyplnen orchestration checklist
- doporuceny branch protection setting je: `Require status checks` -> `orchestration-release-gate`
- zatim zamerne nevyzadujeme `require code owners`
- helper pro branch protection dry-run/apply je v `scripts/enable_orchestration_required_check.py`

## Stability Check

Pred nastavenim jako required status check musi gate zustat stabilni.

Aktualni lokalni overeni:

- 3 po sobe jdoucí runy byly green
- namerene trvani bylo priblizne `42-44 s`
- gate nepouziva externi sitove dependency; v CI potrebuje jen standardni test DB service

Pokud by se gate stal flaky nebo vyrazne zpomalil, nema byt dal slepe vynucovan bez opravy.

## Override Path

Required check nesmi vytvorit tlak na obchazeni systemu pri produkcnim fixu.

Minimalni override pravidlo:

- pokud `orchestration-release-gate` failne a je potreba vedomy hotfix
- PR musi mit zaskrtnute `Override requested`
- PR musi obsahovat explicitni justification v sekci `Orchestration Notes`
- reviewer musi override vedome potvrdit v review

Tohle je zatim manualni process guard, ne automatizovany bypass.

Samostatny governance rehearsal runbook je v `docs/orchestration_governance_drill.md`.

## Release Rule

- zadna z uvedenych sad nesmi failnout
- zadna z uvedenych sad nesmi byt preskocena
- zmena orchestration core bez rerunu tohoto gate neni povolena
- pokud se meni orchestration kontrakt, musi se zmenit i odpovidajici audit testy a dokumentace

## Scope

Tento gate je zamerne uzky. Chrani aktualni orchestration kernel, dispatch ownership, impossible-state guards a recovery rehearsal kontrakt.
