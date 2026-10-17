# Storage Backend Audit 2026-04-05

## Verdikt

Aktuální stav je `blocked`, nikoli `storage-safe`.

Důvod není jen teoretický:

- běžící runtime používá `STORAGE_BACKEND=local`, `storage_authoritative=false`, `APP_ENV=development`, takže produkční S3 kontrakt není v této instanci runtime ověřený
- reálný storage consistency report je dnes rozbitý: vrací `scan_partial`, `db_to_s3=not_executed`, `s3_to_db=not_executed`, protože lokální backend odmítá prefix `analysis-jobs/*`
- živý storage strom obsahuje `23` export objektů v `storage/exports/*`, zatímco DB má aktuálně `0` export záznamů se `storage_key`
- delete kontrakt není skutečně fail-closed: lokální i S3 backend chybu delete jen zalogují a nepropagují ji zpět volajícímu

To znamená, že storage vrstva má několik dobrých fail-closed prvků pro write flow, ale dnešní runtime není dostatečně auditovatelný ani konzistentní pro pilotní bezpečný provoz.

## A) Aktuální storage kontrakt

### Runtime potvrzený kontrakt

- Běžící instance je v `development` profilu a používá `STORAGE_BACKEND=local`.
- `storage_authoritative=false`, takže storage není v této instanci považovaný za autoritativní source of truth.
- DB v aktuálním runtime drží storage keys, ne public URL:
  - `project_photos` se `storage_key`: `121`
  - `project_exports` se `storage_key`: `0`
  - `analysis_jobs` s `input_payload_storage_key`: `0`
- Sample photo storage keys v DB jsou relativní cesty typu:
  - `projects/prj_1/detail-window.jpg`
  - `projects/prj_1/preview/detail-window.jpg`
  - `projects/prj_1/ai/detail-window.jpg`
- Lokální storage strom dnes obsahuje:
  - `projects/*`: `356` objektů
  - `exports/*`: `23` objektů

### Kódový kontrakt

- Backend i worker používají stejný storage dispatcher `app.storage.backend`; není tam silent fallback na jiný backend.
- V produkčním nebo staging profilu konfigurace zakazuje `STORAGE_BACKEND=local` a vyžaduje `STORAGE_BACKEND=s3` + `STORAGE_AUTHORITATIVE=true`.
- Photo upload flow:
  - nejdřív zapisuje originál do storage
  - potom vytváří DB řádek
  - při DB fail po storage write se pokouší originál uklidit
- Photo variant flow:
  - zapisuje preview a AI input
  - při partial failure smaže již zapsané varianty, vynuluje metadata a přepne foto do `failed`
- Export flow:
  - DB řádek vzniká nejdřív jako `pending`
  - `completed` se nastaví až po storage write a následném `storage_key_exists()` probe
  - pokud artefakt po write není ověřený, export fail-closed spadne do `failed`
- Soft delete foto:
  - API nastaví foto na `pending_delete`
  - worker cleanup maže storage a teprve pak přepíná DB stav na `deleted`
- Expired export cleanup:
  - nejdřív maže storage objekt
  - potom maže DB řádky
- Analysis payload offload kontrakt v kódu používá `analysis-jobs/{job_id}/input-payload.json`.

## B) Co je robustní

- Produkční config guardy jsou poměrně silné:
  - `local` storage je v strict prostředí zakázaný
  - neznámý backend je rejectnutý, ne fallbacknutý
  - S3 bucket, region, timeouty a signed URL TTL mají validaci
  - v strict prostředí musí zůstat `storage_authoritative=true`
- DB model nepoužívá křehké public URL jako perzistentní pravdu; runtime vzorek potvrzuje storage keys.
- Photo create flow řeší důležitý případ `storage success + DB fail` lépe než většina ostatních cest: originál se při DB fail uklízí.
- Export flow je správně fail-closed pro `DB success + storage fail` i pro `storage write bez ověřitelného artefaktu`.
- `completed` export se při čtení znovu validuje přes `storage_key_exists()`, a pokud artefakt chybí, záznam je degradovaný do `failed`.
- Storage orphan cleanup má bezpečnostní brzdy:
  - `safe_mode`
  - `minimum_orphan_age_seconds`
  - approval token pro destruktivní cleanup
- Authenticated `/mock-storage/...` route je omezená na `projects/*` a `exports/*` a respektuje tenant access.

### Cíleně ověřené testy 2026-04-05

- `python-backend/tests/test_storage_consistency_service.py` + `python-backend/tests/test_export_ttl_management.py`: `18 passed`
- Tyto testy pokrývají:
  - orphan cleanup safe mode / destructive mode / approval token
  - fail-closed export při chybějícím artefaktu
  - degradaci `completed -> failed`, když storage artefakt zmizí
  - cleanup expired exportů

## C) Slabá místa a data-loss rizika

### 1. Produkční storage backend není v běžícím runtime vůbec ověřený

- Aktuální runtime není S3 runtime, ale lokální disk.
- Nelze tedy tvrdit, že produkční storage je dnes runtime-prokázaný.
- Máme jen deklarovaný kódový kontrakt a unit/integration testy.

### 2. Storage consistency / recoverability check je v živém runtime rozbitý

Tvrdě prokázáno:

- `StorageConsistencyService.build_consistency_report()` v běžící instanci vrací:
  - `scan_status=scan_partial`
  - `db_to_s3=not_executed`
  - `s3_to_db=not_executed`
  - `error_detail="Invalid storage key: only 'projects/' and 'exports/' storage paths are allowed."`

Kořen problému:

- consistency scan listuje `projects`, `exports` a `analysis-jobs`
- lokální storage backend dovolí jen `projects` a `exports`
- analysis payload offload kontrakt ale generuje klíče `analysis-jobs/...`

To blokuje runtime auditovatelnost i self-healing, protože systém neumí udělat plný DB <-> storage scan ani v development runtime.

### 3. Analysis payload offload je s lokálním backendem fakticky nefunkční

Tvrdě prokázáno runtime probe:

- pokus zapsat `analysis-jobs/runtime-check/input-payload.json` skončil:
  - `ValueError`
  - `"Invalid storage key: only 'projects/' and 'exports/' storage paths are allowed."`

Praktický dopad:

- jakmile v lokálním runtime nastane payload offload, write selže na storage policy mismatch
- jde o latentní failure, který se neprojeví při malých payloads, ale objeví se až při větším vstupu nebo blobu

### 4. Runtime už teď obsahuje orphan export objekty

Tvrdě prokázáno:

- storage `exports/*`: `23` objektů
- DB export řádky se `storage_key`: `0`

To znamená minimálně:

- storage a DB už dnes nejsou v konzistentním export kontraktu
- cleanup / retention flow není uzavřený
- současný broken consistency scan tyto orphan exporty neumí korektně zreportovat

### 5. Delete kontrakt není skutečně fail-closed

Lokální i S3 backend mají stejný problém:

- při delete failure jen zalogují `storage.delete_failed`
- výjimku dál nevyhodí

Praktický dopad:

- `_delete_storage_keys_fail_closed()` není ve skutečnosti fail-closed, protože backend delete neskončí exception
- `cleanup_pending_deletes()` může označit foto jako `deleted`, i když storage objekt reálně zůstal
- `cleanup_orphans()` může reportovat orphan delete jako hotový, i když backend delete selhal
- `delete_expired_exports()` může pokračovat, i když storage delete neproběhl

To je safety problém, ne jen kosmetika v logování.

### 6. Export flow nemá plně uzavřený případ `storage success + DB fail`

- Export write flow umí fail-closed, když storage write nebo artifact probe selže.
- Když ale storage write a probe uspějí a následně selže DB update do `completed`, nevzniká kompenzační cleanup artefaktu.

Riziko:

- storage může držet platný objekt bez odpovídajícího DB stavu
- následný cleanup závisí na pozdější reconciliaci, která je dnes navíc částečně rozbitá

### 7. Startup storage validation není v aktuálním runtime fail-fast

- Storage health se na startu ověřuje.
- V `development/test` prostředí ale backend po storage failure pouze degraduje a může pokračovat dál.

To je pro dev workflow přijatelné, ale pro pilotní nebo production-like runtime je to příliš měkké.

### 8. Test coverage je slušná, ale ne úplně spolehlivá jako provozní důkaz

Širší storage sada dnes není plně zelená:

- `154` testů spuštěno
- `149 passed`
- `5 failed`

Selhání nejsou primárně důkazem storage runtime pádu, ale ukazují drift test harnessu:

- jeden storage cleanup test používá incomplete fake settings
- čtyři preview testy naráží na rate-limit wrapper bez `Request`

To snižuje důvěru, že storage regression suite dnes přesně reprezentuje reálný runtime kontrakt.

## D) Priority fixů P0-P3

### P0

- Srovnat storage key policy:
  - lokální backend musí explicitně podporovat `analysis-jobs/*` pro interní storage operace
  - storage consistency scan pak musí být schopný doběhnout do plného výsledku
- Opravit delete semantics:
  - backend delete musí při reálném failure vyhazovat exception
  - best-effort cleanup má být explicitní wrapper v service vrstvě, ne tiché chování backendu
- Vyčistit a znovu změřit runtime export orphany:
  - minimálně těch `23` objektů v `storage/exports/*`
  - cleanup až po čerstvém dry-run consistency reportu

### P1

- Doplnit kompenzaci pro `storage success + DB fail` v export flow:
  - po selhání DB update se pokusit artefakt smazat
  - pokud cleanup selže, zapsat explicitní auditovatelný error stav
- Zpřísnit startup / readiness kontrakt pro pilot:
  - pilot nesmí běžet na `local` backendu
  - `scan_partial` storage consistency musí být blocker, ne jen warning
- Přidat storage drift alerty:
  - orphan count
  - scan partial
  - delete failure
  - write failure

### P2

- Přidat explicitní testy pro `storage success + DB fail` u exportů a analysis payload offloadu.
- Rozlišit v logování a chybové klasifikaci:
  - timeout
  - auth/config failure
  - missing object
  - transient transport error
- Přidat periodický read-only consistency dry-run do provozní observability.

### P3

- Udržet storage validation suite bez harness driftu, aby šla použít jako release gate.
- Přidat metriku stáří orphan objektů a trend orphan growth.

## E) Minimální patch návrhy

### 1. Oprava prefix driftu bez redesignu

- V `local_photo_storage` rozšířit `_ALLOWED_STORAGE_PREFIXES` o `analysis-jobs`.
- Nenechávat `analysis-jobs` veřejně servovat přes `/mock-storage`; to má zůstat neveřejné.
- Doplnit test, že local backend:
  - umí `write/read/delete/list` pro `analysis-jobs/*`
  - ale route `GET /mock-storage/analysis-jobs/...` stále vrací `404`

### 2. Tvrdý delete kontrakt

- `delete_storage_file()` musí při delete failure vracet exception.
- Service vrstvy rozdělit:
  - best-effort cleanup: log + pokračovat
  - fail-closed delete: exception = žádná změna DB stavu

### 3. Export kompenzace po DB fail

- Obalit `repository.update_state(... completed ...)` try/except blokem.
- Pokud DB update selže po úspěšném storage write:
  - pokusit se storage objekt ihned smazat
  - logovat explicitní `export.persistence_failed_after_storage_write`
  - nenechat tichý orphan artefakt bez záznamu

### 4. Storage consistency jako gate

- Přidat jednoduchý operational check:
  - `storage_consistency_scan_status`
  - `orphan_export_count`
  - `missing_storage_object_count`
- Pilot readiness musí být `red`, pokud consistency scan neběží plně nebo hlásí blockery.

## F) Testy po opravách

### 1. Upload failure mid-flight

- Simulovat partial variant write:
  - preview write uspěje
  - ai_input write selže
- Očekávání:
  - preview objekt je uklizený
  - AI metadata jsou nulovaná
  - photo `processing_status=failed`
  - v DB nezůstane reference na neexistující variantu

### 2. Storage timeout

- Simulovat timeout při `write_storage_file`, `read_storage_file` a `storage_key_exists`.
- Očekávání:
  - export/photo flow spadne do deterministického `failed`, ne do nekonečného retry
  - log obsahuje klasifikaci `timeout`
  - readiness / operational metrics timeout reflektují

### 3. Stale object cleanup

- Vytvořit orphan objekty v `exports/*` a `analysis-jobs/*`.
- Spustit dry-run consistency scan.
- Očekávání:
  - správný orphan count
  - approval token
  - destructive cleanup smaže jen objekty starší než minimum age
  - po cleanup je scan čistý

### 4. DB success + storage fail

- Export:
  - vytvořit `pending/generating` DB řádek
  - storage write nebo artifact probe selže
- Očekávání:
  - export končí jako `failed`
  - `storage_key=None`
  - nezůstane completed záznam bez artefaktu

### 5. Storage success + DB fail

- Foto:
  - originál se zapíše do storage
  - DB insert selže
- Očekávání:
  - originál je uklizený
  - v storage nic nezůstane

- Export:
  - storage write a probe uspějí
  - DB update do `completed` selže
- Očekávání:
  - artefakt je kompenzačně smazaný
  - vznikne auditovatelný error event
  - následný consistency scan nenajde orphan export

## G) Verdikt

`blocked`

Systém dnes není `storage-safe`.

Prokázané plusy:

- DB drží storage keys místo public URL
- photo create a export fail-closed flow jsou částečně dobré
- produkční config guardy jsou rozumně přísné

Prokázané blockery:

- běžící runtime není na produkčním storage backendu
- consistency scan je v live runtime částečně nefunkční
- local backend neumí `analysis-jobs/*`, přesto je kód používá
- export storage už dnes obsahuje orphan objekty
- delete flow není skutečně fail-closed

Dokud nebudou opravené minimálně P0 položky, storage vrstvu nelze označit za pilot-safe ani auditovatelně recoverable.
