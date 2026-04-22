# Orchestration Governance Drill

Tento runbook overuje, ze governance funguje nejen technicky, ale i procesne:

- gate opravdu failne pri poruseni orchestration contractu
- override flow je vedomy a auditovatelny
- nic se neobchazi bokem mimo PR process

## Preconditions

- validni `gh` auth pro repo
- branch protection na `master` ma required status check `orchestration-release-gate`
- reviewer zna override pravidlo z `docs/orchestration_release_gate.md`

## 1. Zapnout Required Check

Nejdriv udelej dry run:

```powershell
python scripts/enable_orchestration_required_check.py
```

Pokud payload vypada spravne, aplikuj ho:

```powershell
python scripts/enable_orchestration_required_check.py --apply
```

## 2. Vytvorit Test PR

Vytvor branch typu:

```text
chore/orchestration-governance-drill
```

Do branch udelej zamerne neprodukční zmenu, ktera shodi gate.

Nejjednodussi drill:

- v `python-backend/tests/test_orchestration_invariant_guards.py`
- pridej docasne failing assertion s textem `governance drill`

Napriklad:

```python
def test_governance_drill_intentional_failure() -> None:
    assert False, "governance drill"
```

Tenhle commit nesmi byt mergnut do `master`.

## 3. Otevrit PR

V PR:

- vypln `Orchestration Impact`
- zaskrtni `Protected orchestration files changed in this PR`
- zaskrtni `Override requested`
- do `Orchestration Notes` napis:
  - impacted commands / rules / invariants
  - gate result = intentional failure for governance drill
  - explicitni justification

## 4. Overit Chovani

Ocekavany vysledek:

- `orchestration-release-gate` failne
- PR template obsahuje override justification
- reviewer explicitne potvrdi override v review
- PR se nemerguje

## 5. Drill Uklidit

Po overeni:

- zavri PR bez merge
- smaz branch
- neponechavej failing test v aktivni branch

## Success Criteria

- governance stack zafungoval technicky
- governance stack zafungoval procesne
- nikdo nemusel obchazet dispatch registry, invarianty ani branch protection
