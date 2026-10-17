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

**Ledger trvalých smazání:**
- Každé trvalé smazání zapíše strukturovaný řádek `photo.purge_authorized` (s `photo_id`, `case_id`, `org_id`, `actor_id` a `action`) a audit v DB.
- Archiv logů se zálohuje **odděleně od DB** a musí mít retenci **alespoň o měsíc delší, než je nejdelší retence záloh (≥ 7 měsíců)**. Jinak by se po obnově staré zálohy nevědělo, co znovu smazat.

**Postup po obnově ze zálohy pořízené v čase T:**
1. Nechat aplikaci v údržbě (backend a worker zastavené).
2. Z archivu logů vybrat ID smazaných fotek novější než T, například:
   ```bash
   journalctl -u novu-backend --since "<T>" -o cat \
     | grep '"photo.purge_authorized"' | jq -r .photo_id | sort -u > purged_ids.txt
   ```
3. Smazání znovu provést:
   ```bash
   python -m scripts.reapply_photo_purges --confirm --from-file purged_ids.txt
   ```
   Skript je idempotentní, audituje (`system.image.purge`) a používá stejný dvoufázový postup. Fotky, které v obnovené DB nejsou, přeskočí.
4. Spustit worker. Ten dokončí případné `purge_pending` i soft delete, kterým během výpadku vypršela retence (`deleted_at` se zálohou zachová).
5. Zkontrolovat, že `SELECT count(*) FROM project_photos WHERE status = 'purge_pending'` vrací 0, a teprve pak aplikaci otevřít.

## 6. Zbývající rizika

- **Snímky odeslané AI providerovi** (Anthropic) před smazáním smazat nelze. Řídí je retenční politika providera.
- **Podepsané odkazy vydané před soft delete** fungují do vypršení TTL (≤ 1 h). Pro okamžité zneplatnění je potřeba použít trvalé smazání.
- **Kopie u uživatelů:** fotky stažené nebo exportované před smazáním (ZIP, PDF u uživatele) jsou mimo systém.
- **Ledger je jen tak spolehlivý jako archiv logů.** Pokud se logy ztratí, dá se pro obnovu použít audit z nejnovější dostupné zálohy DB, ale smazání novější než ta záloha se tím nepokryjí.
