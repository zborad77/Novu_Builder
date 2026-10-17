# NovuConstruct – Vlastnictví a mazání fotografií

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | Implementováno ve větvi `fix/f0-rbac-tenant-isolation` (F0.3), **zatím nevydáno** |
| **Kód** | `app/core/rbac.py` (`can_soft_delete_photo`, `can_purge_photo_in_tenant`), `app/api/routes/images.py`, `app/api/photo_purge.py`, `app/services/photo_service.py`, `scripts/reapply_photo_purges.py` |
| **Migrace** | `20261017_0058` (soft delete), `20261017_0059` (autor, stav `purge_pending`) |
| **Související** | [RBAC_ROLE_MATRIX.md](RBAC_ROLE_MATRIX.md) §2.5 |

## 1. Stavy fotografie

```
            DELETE (soft)                     worker po PHOTO_DELETE_RETENTION_HOURS
  active ──────────────────► pending_delete ──────────────────────────────────────► deleted
    ▲   ◄────────────────────      │                                                   ▲
    │        POST …/restore        │ POST …/purge (admin)                               │
    │                              ▼                                                    │
    └──── POST …/purge ───► purge_pending ──── soubory smazány (API nebo worker) ───────┘
```

| Stav | Viditelná v API, detailu a exportech | Lze obnovit | Soubory v úložišti |
|---|---|---|---|
| `active` | ano | – | ano |
| `pending_delete` | ne (jen v koši) | ano | ano, do konce retence |
| `purge_pending` | ne | **ne** | mažou se, worker opakuje |
| `deleted` | ne | ne | ne |

## 2. Kdo smí co

| Operace | superadmin | admin (firma) | manager | technician |
|---|---|---|---|---|
| Soft delete (`DELETE /cases/{id}/images/{image_id}`) | ✅ | ✅ fotky své firmy | ✅ fotky své firmy | ✅ **jen vlastní** fotky (`uploaded_by_user_id` = on) |
| Koš (`GET /cases/{id}/images/deleted`) | ✅ | ✅ | ✅ | ✅ jen vlastní |
| Obnova (`POST …/images/{image_id}/restore`) | ✅ | ✅ | ✅ | ✅ jen vlastní |
| Trvalé smazání přes zakázku (`POST …/images/{image_id}/purge`) | ❌ (musí použít systémovou správu) | ✅ jen své firmy | ❌ | ❌ |
| Trvalé smazání systémově (`POST /admin/photos/{photo_id}/purge`) | ✅ | ❌ | ❌ | ❌ |

Kontroly na každém požadavku: tenant (cizí zakázka 404) → zakázka (fotka musí patřit k zakázce v URL, jinak 404) → role → vlastnictví.

**Autor:**
- `uploaded_by_user_id` nastavuje výhradně server z ověřeného tokenu při uploadu. Formulář ani API nemají pole, kterým by šel autor zadat nebo změnit.
- Fotky z doby před migrací `0059` mají autora `NULL`, což znamená, že nepatří nikomu. Spravuje je jen manager nebo admin.

**Deaktivovaný nebo odstraněný autor:**
- **Deaktivace:** autorův token přestane platit (401), fotky zůstanou a dál je spravuje manager nebo admin. Po reaktivaci je autor znovu vlastníkem.
- **Odstranění účtu:** cizí klíč `ON DELETE SET NULL` vynuluje vlastnictví a fotka se chová jako fotka bez autora. Nové ID uživatele se nikdy nepoužije znovu, takže se vlastnictví nemůže přenést na jiného člověka.

## 3. Trvalé smazání

**Požadavek:** `{"confirmImageId": "<stejné id jako v URL>"}`. Jiná hodnota vrací 400, chybějící 422.

**Odpověď:**
- `200 {"status":"purged"}`: soubory jsou smazané.
- `202 {"status":"purge_pending"}`: úložiště nebylo dostupné, dokončí to worker.

**Průběh:**
1. **Jedna DB transakce s auditem (fail-closed):**
   - fotka přejde do `purge_pending`,
   - všechny exporty zakázky se okamžitě zneplatní (`expires_at = now`), protože mohou fotku obsahovat,
   - zapíše se audit `image.purge`, `admin.image.purge` nebo `system.image.purge`.

   Když audit nejde zapsat, vrátí se 503 a nic se nezmění. Do logu jde řádek `photo.purge_authorized`, který slouží jako „ledger“ pro zálohy (kap. 5).
2. **Smazání originálu, náhledu a AI varianty** z úložiště. Mazání je idempotentní (chybějící objekt není chyba).
   - Teprve po úspěchu všech tří přejde fotka do `deleted`.
   - Když selže kterýkoli objekt, fotka zůstane `purge_pending`. Worker ji při každém úklidu (každých 30 s, bez čekání na retenci) zkusí znovu.
   - Opakovaný API požadavek dokončí totéž a nezapíše druhý audit.

**Konzistence:**
- Řádek je v `deleted` jen tehdy, když jsou smazané všechny jeho objekty. Osiřelé soubory tak nevzniknou a řádek se neztratí.
- Pád backendu mezi fázemi nevadí: fotka zůstane `purge_pending` a worker ji dokončí.

## 4. Co uživatel po smazání neuvidí

| Kanál | Soft delete | Trvalé smazání |
|---|---|---|
| `GET /cases/{id}/images`, detail zakázky | skryto okamžitě | skryto okamžitě |
| `GET /images/{id}/preview` | 404 | 404 |
| Exporty vytvořené **po** smazání | fotka chybí | fotka chybí |
| Exporty vytvořené **před** smazáním | dostupné do expirace (`EXPORT_TTL_DAYS`) | **404 okamžitě**, soubory smaže úklid exportů |
| Dříve vydané podepsané odkazy (S3, TTL ≤ `STORAGE_SIGNED_URL_TTL_SECONDS`, max. 1 h) | fungují do vypršení TTL | přestanou fungovat smazáním objektů (po fázi 2) |
| Lokální úložiště (`/mock-storage`, jen development) | soubor existuje do retence | soubor smazán |

## 5. Zálohy: retence a výmaz

**Retence záloh** (podle [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) §8.4):

| Typ | Retence |
|---|---|
| denní | 7 |
| týdenní | 4 |
| měsíční | 6 |
| WAL | 7 dní |

Trvale smazaná fotka tak může v zálohách přežít **nejvýše ~6 měsíců**. Zálohy jsou šifrované, přístupné jen správcům a slouží jen k obnově po havárii. Jednotlivé soubory se z nich nevyřezávají, protože by to porušilo integritu a ověřitelnost záloh. Výmaz je úplný, když vyprší poslední záloha, která fotku obsahuje. Tuto lhůtu je potřeba uvést v informacích o zpracování osobních údajů.

**Ledger trvalých smazání** (`app/core/purge_ledger.py`):
- Je to append-only soubor JSONL **mimo databázi** (`PHOTO_PURGE_LEDGER_PATH`, např. `/var/lib/novu/photo-purge-ledger.jsonl`).
- Každé trvalé smazání se do něj zapíše **před** commitem DB transakce, s `flush` a `fsync`. Záznam obsahuje `ts`, `photo_id`, `case_id`, `org_id`, `actor_id` a `action`.
- Když zápis selže, smazání se neprovede (503). Mimo development bez nastaveného ledgeru se trvalé smazání odmítne (503).
- Pokud DB commit po zápisu do ledgeru selže, zůstane v ledgeru jen záznam o autorizovaném záměru. Jeho opakované provedení po obnově je neškodné.
- Druhou nezávislou kopií je řádek `photo.purge_authorized` v aplikačním logu.
- Obnova DB vrátí zpět i `audit_logs`, ledger ale ne. Proto podle něj jde smazání zopakovat. Ověřeno testem `test_purge_ledger_survives_database_restore_and_drives_reapply`, který simuluje obnovu (fotka znovu `active`, audit pryč) a spouští re-apply.
- **Ledger musí přežít ztrátu serveru:** soubor se průběžně kopíruje mimo server (log shipping nebo samostatný restic snapshot častěji než záloha DB). Retence ledgeru a archivu logů musí být **alespoň o měsíc delší, než je nejdelší retence záloh (≥ 7 měsíců)**.

**Postup po obnově ze zálohy pořízené v čase T:**
1. Nechat aplikaci v údržbě (backend a worker zastavené).
2. Smazání znovu provést podle ledgeru (nejnovější kopie mimo server):
   ```bash
   python -m scripts.reapply_photo_purges --confirm      --ledger /var/lib/novu/photo-purge-ledger.jsonl --since "<T jako ISO 8601 s offsetem>"
   ```
   Skript je idempotentní, audituje (`system.image.purge`) a používá stejný dvoufázový postup. Fotky, které v obnovené DB nejsou, přeskočí.

   Když ledger chybí, ID se vyberou z archivu logů:
   ```bash
   journalctl -u novu-backend --since "<T>" -o cat | grep '"photo.purge_authorized"' | jq -r .photo_id | sort -u > purged_ids.txt
   python -m scripts.reapply_photo_purges --confirm --from-file purged_ids.txt
   ```
3. Spustit worker. Ten dokončí případné `purge_pending` i soft delete, kterým během výpadku vypršela retence (`deleted_at` se zálohou zachová).
4. Zkontrolovat, že `SELECT count(*) FROM project_photos WHERE status = 'purge_pending'` vrací 0, a teprve pak aplikaci otevřít.

## 5a. Odkazy na trvale smazanou fotku

| Kde | Chování |
|---|---|
| Markery (`markers.image_id`) | **smažou se** ve stejné transakci jako trvalé smazání, protože jsou to anotace vymazaného obsahu. Počet je v auditu (`markers_deleted`). Soft delete markery nemaže (obnova je vrátí v původní podobě). |
| Výsledky analýzy a měření (`analysis_results.reference_photo_id`) | **nemění se**. Historická měření a rozpočty zůstávají platné i bez obrázku, ID fotky zůstává jako auditní stopa. Fotka sama vrací 404. |
| Vision detekce (`vision_detections.reference_photo_id`) | historické se nemění |
| Nové odkazy (marker, `referenceImageId` u měření, `referencePhotoId` u detekce) | jen na **aktivní** fotku stejné zakázky. Smazaná nebo trvale smazaná fotka vrací 422 nebo 404. |
| Odpověď fotky | aditivní pole `uploadedByUserId` a `canDelete` (oprávnění aktuálního uživatele ke smazání/obnově). Stávající klienti je mohou ignorovat. |

## 5b. Podepsané URL a soft delete: rozbor a návrh

**Stav:**
- Odpovědi se seznamem fotek obsahují presigned URL na MinIO (originál, náhled, AI varianta) s platností `STORAGE_SIGNED_URL_TTL_SECONDS` (výchozí 3600 s).
- S3 presigned URL nejde odvolat. Po soft delete objekty v úložišti zůstávají kvůli obnově, takže dříve vydaná URL funguje až do konce TTL.
- Trvalé smazání URL zneplatní tím, že smaže objekty.

**Zamítnuté varianty:**
- Veřejný MinIO endpoint s krátkým TTL zakazuje architektura (MinIO jen na loopbacku nebo v privátní síti).
- Přesouvat objekty při soft delete do karanténního prefixu znamená dvojité zápisy a nové chybové stavy. Navíc to neřeší aktivní fotky a odebraná práva.

**Návrh:**
1. **Hned (jen konfigurace):** v produkci `STORAGE_SIGNED_URL_TTL_SECONDS=300`. Okno po soft delete se zkrátí na ≤ 5 min. Klienti si URL znovu obnoví načtením seznamu, platnost stažení exportu je pro běžný workflow dostatečná.
2. **Cíl (plánovaná fáze D-03 / F4.6 v [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)):** URL v odpovědích ukazují na autentizovaný endpoint backendu `GET /api/v1/files/images/{id}/{variant}`.
   - Ten při **každém** požadavku ověří token, firmu, roli a `status = active`.
   - Data posílá nginx přes interní `X-Accel-Redirect` na `internal` location, která proxuje na MinIO (127.0.0.1 nebo WireGuard) s podpisem platným 60 s. Ten podpis klient nikdy nevidí.
   - Výsledek: soft delete, trvalé smazání i odebrání práv platí **okamžitě**, MinIO zůstává neveřejné a návrh funguje stejně přes Public Gateway i WireGuard.
   - Tvar polí `url` a `variants.*.url` zůstane stejný, změní se jen hodnota.

## 6. Zbývající rizika

- **Snímky odeslané AI providerovi** (Anthropic) před smazáním smazat nelze. Řídí je retenční politika providera.
- **Podepsané odkazy vydané před soft delete** fungují do vypršení TTL (≤ 1 h, s doporučeným nastavením ≤ 5 min). Okamžité zneplatnění zajistí jen trvalé smazání, dokud nebude hotový autentizovaný endpoint (§5b).
- **Kopie u uživatelů:** fotky stažené nebo exportované před smazáním (ZIP, PDF u uživatele) jsou mimo systém.
- **Ledger je jen tak spolehlivý jako jeho kopie mimo server.** Když se ztratí ledger i archiv logů, smazání novější než obnovená záloha nejde dohledat.
