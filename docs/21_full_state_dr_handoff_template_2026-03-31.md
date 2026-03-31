# Full-State DR Handoff Template

Vypln po dokonceni restore operace.

## 1. Identifikace

- Operator:
- Datum:
- Cas start:
- Cas konec:
- Incident / ticket:

## 2. Backup Set

- Backup file:
- DB manifest file:
- S3 media manifest file:
- Backup scope:
- DR contract:

## 3. Storage Pairing

- Source bucket:
- Source region:
- Declared recovery point:
- S3 object count:
- Isolated restore bucket:
- Isolated restore region:

## 4. Restore Verdict

- Backup set validation:
- Media restore step:
- Media validation step:
- DB restore contract:
- Schema/head alignment:
- Backend liveness:
- Full DB<->storage consistency validation:
- Full-state restore claim:
- Production DR:
- Release readiness decision:

## 5. Evidence

- Restore log file:
- Verify log file:
- Additional notes:

## 6. Handoff Decision

- GO / NO-GO:
- Schvalil:
- Cas handoff:

