# Backup/Restore Readiness Audit

Datum: 2026-04-06
Scope: backup, restore, recoverability, disaster readiness, data integrity, operational confidence

## Verdict

`partially recoverable`

DB restore path je v repo uz pomerne silna a fail-closed: existuje deterministicky artifact set, checksum, manifest contract, non-destructive verify, schema/head validation a post-restore storage consistency gate. Plnohodnotna obnovitelnost celeho systemu ale porad neni dostatecne uzavrena do jedne provozni pravdy. Nejvetsi slabiny jsou neuzavreny RPO/RTO ramec, nejednoznacna dokumentacni truth kolem full-state DR, chybejici integrity coverage pro JSON manifesty a fakt, ze restore dokazujeme hlavne jako izolovany recovery proof, ne jako kompletni production cutover contract.

## A) Co Je Potreba Zalohohovat Jako Autoritativni Data

### 1. PostgreSQL

Autoritativni DB vrstva nese:

- tenant a identity truth
- auth state a revoked token truth
- audit truth
- job truth a processing metadata
- storage metadata a referencni `storage_key` vazby

Prakticky to znamena, ze backup DB musi pokryt minimalne:

- `organizations`
- `users`
- `projects`
- `analysis_jobs`
- `audit_logs`
- `revoked_tokens`
- dalsi relacni tabulky navazane na pricing, exports, role/permissions a stav projektu

Tato cast je v repo pokryta nejlepe:

- `scripts/backup.sh` vytvari `db_*.pgdump` + `.sha256` + `db_*.json`
- `python-backend/scripts/verify_restore.sh` proveruje kriticke tabulky, row presence a `alembic_version`
- `ops/restore.sh` po restore znovu validuje critical tables a schema/head alignment

### 2. S3 Object Storage

Autoritativni storage vrstva nese:

- uploaded photos
- derived photo variants
- AI input variants
- export artifacts

Pro `APP_ENV=production` + `STORAGE_BACKEND=s3` je to skutecna source of truth pro bytes, ne DB. DB sama o sobe po restore nestaci, pokud klicovane objekty v S3 neexistuji nebo nejsou ve spravnem versioned recovery pointu.

### 3. Konfigurace, Secrets A Kriticke Procedury

Z pohledu skutecne obnovitelnosti jsou kriticke i:

- runtime config
- secrets a AWS credentials
- znalost source/target bucketu a recovery pointu
- restore procedury a approval flow

Tady je situace slabsi:

- repo ma detailni runbooky a approval packet
- ale nema automatizovany backup config/secrets state
- restore tak stale predpoklada externi secret/config truth mimo samotny backup set

### 4. Co Neni Autoritativni Backup Target

- Redis neni autoritativni backup target
- local `storage_data` neni production truth
- temp/runtime stav workeru neni source of truth

To je bezpecny design.

## B) Co Uz Je Bezpecne A Provozne Pouzitelne

### 1. Deterministicky DB Backup Contract

Silne stranky:

- custom-format `pg_dump`
- povinny checksum
- manifest se zapisuje az po uspesnem dumpu a checksumu
- dump je failnuty i pri podezrele malem souboru

To znamena, ze DB backup neni jen best-effort archiv, ale pomerne dobre definovany artifact contract.

### 2. Fail-Closed Restore Guardy

`ops/restore.sh` i `verify_restore.sh` failnou pri:

- chybejicim manifestu
- checksum mismatch
- kontraktni nekonzistenci manifestu
- neplatnem production+s3 pairing metadata
- failed verify
- failed `pg_restore`
- schema/head mismatch

To vyrazne snizuje riziko ticheho "restore success", ktery by ve skutecnosti obnovil nevalidni stav.

### 3. Non-Destructive Verify

`python-backend/scripts/verify_restore.sh` umi:

- obnovit dump do temp DB
- zkontrolovat schema/head
- overit kriticke tabulky
- pustit sampled DB->storage validaci

To je silny stavebni blok pro bezpecnou pre-restore kontrolu.

### 4. Reconciliation A Post-Restore Consistency

Repo uz ma pouzitelny post-restore reconciliation nastroj:

- `python-backend/scripts/check_storage_consistency.py`

Ten umi:

- DB->storage blocker scan
- storage->DB orphan scan
- blokovat release readiness pri DB->storage nesouladu

To je dulezite, protoze restore nehodnoti jen "DB nabehla", ale i "DB reference stale ukazuji na realne objekty".

### 5. Safe Full-State Proof Pattern

Full-state S3 path ma jednu velmi dobrou vlastnost:

- media restore jde do izolovaneho restore bucketu
- helper odmitne zapis do source bucketu
- helper odmitne overwrite existujicich target objektu

To omezujet blast radius recovery testu a je to bezpecnejsi nez prime "restore into production bucket".

### 6. Tribal Knowledge Je Snizena, Ne Eliminovana

Pozitivni je, ze full-state DR neni jen v hlavach lidi:

- existuje operator runbook
- incident checklist
- copy-paste playbook
- handoff template
- approval packet

To je nadprumerne dobre zdokumentovane.

## C) Kde Jsou Slaba Mista A Blind Spots

### 1. Neni Ujasneny Jediny Provozni Truth Pro Full-State DR

Tady je dnes nejvetsi provozni rozpor:

- root [BACKUP_RESTORE.md](d:/Novu_Hub/Novu_Builder/BACKUP_RESTORE.md) tvrdi, ze repo full production DR neimplementuje a `production_dr_eligible=false`
- [OPERATIONS.md](d:/Novu_Hub/Novu_Builder/OPERATIONS.md) opakuje DB-only production truth
- ale [docs/BACKUP_RESTORE.md](d:/Novu_Hub/Novu_Builder/docs/BACKUP_RESTORE.md), [docs/18_full_state_dr_operator_runbook_2026-03-31.md](d:/Novu_Hub/Novu_Builder/docs/18_full_state_dr_operator_runbook_2026-03-31.md) a samotne skripty uz zavedly explicitni `db-plus-s3-media-manifest` contract a `Production DR: VERIFIED`

To je operational risk samo o sobe. Pri incidentu musi byt jedna autoritativni pravda, ne dve.

### 2. RPO/RTO Ramec Neni Explicitne Stanoven

Repo sice umi backup a restore flow, ale neudava:

- cilovy RPO
- cilovy RTO
- maximalne pripustnou ztratu dat
- maximalne pripustny cas obnovy

Navic:

- point-in-time recovery je explicitne out of scope
- WAL archiving/PITR neni implementovany
- retenze dumpu sama o sobe neni recovery objective

Prakticky tedy system nema jasne deklarovanou disaster readiness budget truth.

### 3. Offsite/Remote Backup Neni Hard Requirement

`scripts/backup.sh` umi optional remote sync, ale:

- je nepovinny
- failure remote syncu nemeni exit code lokalniho backupu
- syncuje DB dump, checksum a DB manifest
- full-state S3 media manifest se do `SYNC_FILES` nepridava

To je vyznamna dira:

- lokalni backup muze skoncit "success", i kdyz offsite kopie neexistuje
- full-state metadata muzou zustat jen lokalne

Z pohledu DR je to nebezpecne optimisticke.

### 4. Integrity Coverage Konci U DB Dumpu

Checksum je povinny pouze pro `db_*.pgdump`.

Chybi:

- checksum/signature pro `db_*.json`
- checksum/signature pro `db_*.s3-media.json`

Restore sice kontroluje semantiku a pairing, ale ne kryptografickou integritu techto JSON artefaktu. To znamena, ze proti tiche manipulaci nebo corruption je ochrana jen parcialni.

### 5. Full-State Media Restore Overuje Hlavne Size, Ne Silnou Objektovou Integritu

`python-backend/scripts/restore_s3_media.py` po copy kontroluje:

- ze objekt vznikl
- ze `ContentLength` odpovida

Ale neoveruje plne:

- checksum/etag shodu
- pripadne dalsi integrity metadata

Na recovery proof je to slusne, na silny integrity claim je to porad mekke.

### 6. Restore Nepotvrzuje Celou Provozni Readiness

`ops/restore.sh` po restartu kontroluje hlavne:

- backend liveness
- schema/head
- storage consistency gate

Nepotvrzuje ale explicitne:

- worker readiness / heartbeat
- auth smoke
- tenant-facing login flow
- end-to-end processing readiness

To znamena, ze restore muze byt oznacen jako handoff-ready, i kdyz asynchronni zpracovani nebo auth runtime jeste nejsou zdrave.

### 7. Config/Secrets Recovery Neni Soucasti Artifact Setu

Full obnovitelnost dnes porad predpoklada:

- dostupne AWS credky
- spravne env vars
- bucket names, region, recovery point
- runtime config

Existuji runbooky, ale neexistuje automatizovany config snapshot nebo formalni external source-of-truth contract. To je typicka oblast, kde incident restore zacina zaviset na operational memory.

### 8. Test Coverage Je Realna, Ale Ne Dostatocne Routine-Proven

`python-backend/tests/test_backup_restore_e2e.py` v tomto prostredi probehl jako:

- `4 passed, 86 skipped`

Skip reason ukazuje, ze velka cast bash-backed restore E2E neni v tomhle runneru spustitelna kvuli Git Bash/Windows chybe. To nesnizuje hodnotu designu, ale snizuje confidence, ze je cely restore contract opravdu bezne a opakovane prokazovan v CI/runtime prostredi.

## D) Priority Fixu P0–P3

### P0

- Sjednotit jednu autoritativni production truth pro backup/restore. Bud oficialne potvrdit full-state S3 kontrakt jako supported, nebo ho vratit na experimental status. Root [BACKUP_RESTORE.md](d:/Novu_Hub/Novu_Builder/BACKUP_RESTORE.md), [OPERATIONS.md](d:/Novu_Hub/Novu_Builder/OPERATIONS.md), [docs/BACKUP_RESTORE.md](d:/Novu_Hub/Novu_Builder/docs/BACKUP_RESTORE.md) a runbooky dnes nesmi mluvit ruzne.
- Zavezt explicitni RPO/RTO policy. Minimalne deklarovat, zda je akceptovany dump-only model, nebo je pro production potreba WAL/PITR.
- Udelat offsite backup success autoritativni soucast backup verdictu. Pokud je disaster readiness cil, remote copy failure nesmi koncit zelenym "backup complete".

### P1

- Pridat checksum nebo podpis pro `db_*.json` a `db_*.s3-media.json`, a v restore je povinne overovat.
- Do remote syncu pridat `db_*.s3-media.json`, pokud je `backup_scope=db-plus-s3-media-manifest`.
- Rozsirit restore gate o worker readiness a alespon minimalni auth smoke.
- Formalizovat config/secrets recovery source:
  - secret manager / vault source
  - IaC location
  - versioned env inventory

### P2

- Posilit objektovou integritu po S3 restore:
  - pouzit checksum metadata nebo silnejsi content verification
  - ne jen size equality
- Automatizovat generation evidence bundle po restore:
  - backup manifest
  - media manifest
  - verify log
  - restore log
  - handoff packet JSON/MD
- Udelat staging restore drill, ktery pravidelne prokazuje i full-state cestu.

### P3

- Sjednotit naming a dokumentacni vrstvu tak, aby operator nemusel rozlisovat root boundary doc vs docs implementation doc bez jasneho precedence modelu.
- Zlepsit Windows/CI spustitelnost bash-backed E2E suite, aby se podstatna cast restore flow neskipovala.

## E) Bezpecne Invarianty

### 1. Authority Invariants

- PostgreSQL je authoritative pro relacni, auth, audit a job metadata.
- S3 je authoritative pro media bytes.
- Redis neni backup source of truth.
- local filesystem storage neni production truth pri `STORAGE_BACKEND=s3`.

### 2. Backup Invariants

- Backup se nesmi oznacit jako disaster-ready jen kvuli lokalnimu DB dumpu.
- Full-state backup claim plati jen kdyz existuje:
  - DB dump
  - DB checksum
  - DB manifest
  - S3 media manifest
  - offsite durability verdict
- JSON metadata musi byt integrity-protected stejne jako DB dump.

### 3. Restore Invariants

- DB restore success neni totiz full-system restore success.
- Full-state restore claim je pravdivy jen po:
  - isolated media restore
  - media usability validation
  - full DB<->storage consistency check
  - backend readiness
  - worker readiness
  - minimal auth smoke

### 4. Operational Invariants

- Restore nesmi zapisovat do source production bucketu.
- Restore nesmi zaviset na tribal knowledge, jen na explicitnich runboocich a externalized config source.
- Po restore musi existovat auditovatelny evidence bundle a jednoznacny GO/NO-GO verdict.

## F) Ověření A Prakticke Drill Scenare

### 1. Minimalni bezpecne pravidelne ověření

Provadet aspon:

1. `scripts/backup.sh`
2. `python-backend/scripts/verify_restore.sh`
3. `ops/restore.sh` proti staging restore targetu
4. `python-backend/scripts/check_storage_consistency.py --mode full`
5. manual nebo automaticky auth + worker smoke

### 2. Povinne negativni scenare

- checksum mismatch DB dumpu
- DB manifest tamper
- S3 media manifest tamper
- missing remote/offsite copy
- missing runtime secrets
- missing S3 object / wrong object version
- worker nenabehne po restore
- backend je live, ale auth nebo processing readiness selze

### 3. Co Musi Být Zaznamenano

- presny backup artifact set
- recovery point
- restore target bucket
- verify output
- restore output
- storage consistency verdict
- finalni GO/NO-GO

## G) Zaver

System neni backup-blind a ma nadprumerne dobry DB restore zaklad. Neni to stav "restore only by folklore". Zaroven ale jeste nejde tvrdit plnou operational confidence pro disaster recovery bez doplneni tri veci:

- jedna nesporná production truth pro full-state DR
- explicitni RPO/RTO a offsite durability contract
- silnejsi integrity a readiness gate i mimo samotnou DB

Dokud tyto body nebudou uzavrene, je ferovy verdict:

`partially recoverable`

DB je obnovitelna pomerne presvedcive. Cely system je obnovitelny slusne navrzenym smerem, ale jeste ne dost tvrde a jednoznacne uzavrenym provoznim kontraktem.
