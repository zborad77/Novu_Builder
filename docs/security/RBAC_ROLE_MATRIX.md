# NovuConstruct – Matice rolí a oprávnění (RBAC)

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | Implementováno ve větvi `fix/f0-rbac-tenant-isolation` (F0 + SA-06 varianta A), **zatím nevydáno**. |
| **Zdroj pravdy v kódu** | [`app/core/rbac.py`](../../src/backend/app/core/rbac.py), závislosti v [`app/api/deps.py`](../../src/backend/app/api/deps.py), migrace `20261017_0057` |
| **Související** | [SECURITY_AUDIT.md](SECURITY_AUDIT.md) (SA-01 až SA-04) · [API_EXPOSURE_MATRIX.md](API_EXPOSURE_MATRIX.md) |

## 1. Dvě oddělené roviny oprávnění

| Rovina | Kdo | Jak se pozná | Rozsah |
|---|---|---|---|
| **Systémová** (správa platformy) | `superadmin` | `users.is_superadmin = true`. Samotný text role nestačí, databáze odmítne `role='superadmin'` bez flagu (`ck_users_superadmin_requires_flag`). | všechny firmy |
| **Firemní** (správa a práce uvnitř jedné firmy) | `admin` ⊃ `manager` ⊃ `technician` | `users.role` + `users.organization_id` | jen vlastní firma |

**Pravidla:**
- Platí deny-by-default: co není povoleno v `app/core/rbac.py`, je zakázáno.
- Tabulku `role_permissions` aplikace pro jiné role než superadmin **nepoužívá**. Migrace `0057` odstranila historické řádky `manager → admin:read/admin:write`.
- Role `superadmin` **nelze přidělit, upravit, deaktivovat ani resetovat přes žádné HTTP API**. Nový superadmin a obnova jeho přístupu jdou jen přes serverový CLI `scripts/create_pilot_admin.py`.
- `organization_id` (tenant) se vždy bere z ověřené identity, nikdy z parametru klienta. Pokus poslat `organizationId`, `organization_id`, `tenant_id` nebo `isSuperAdmin` do admin PATCH skončí **422**.
- Impersonační token se do žádné administrace nedostane (403). Od F3 má `aud=nc-web`, takže ho přijme jen budoucí gateway zóna.
- **Superadmin se přihlásí jen v zóně `admin`** (F3.3). V zónách `gateway` a `desktop` dostane stejnou odpověď jako při špatném heslu.

Role `USER` ze zadání odpovídá stávající roli **`technician`**. Ponechali jsme ji kvůli kompatibilitě s existujícími daty a klienty.

## 2. Matice oprávnění

✅ povoleno · ❌ zakázáno (403) · 🔒 neviditelné (404, jako neexistující záznam) · — nedává smysl

### 2.1 Správa uživatelů (`/api/v1/admin/users*`)

| Operace | superadmin | admin (firma) | manager | technician |
|---|---|---|---|---|
| Seznam uživatelů | ✅ všech firem | ✅ jen své firmy, bez superadminů | ❌ | ❌ |
| Detail uživatele | ✅ | ✅ své firmy · 🔒 cizí firma · 🔒 superadmin | ❌ | ❌ |
| Vytvořit uživatele | ✅ role `admin`/`manager`/`technician` v libovolné firmě | ✅ role `manager`/`technician` jen ve své firmě · 🔒 cizí firma · ❌ role `admin` | ❌ | ❌ |
| Vytvořit `superadmin` | ❌ (422) | ❌ (422) | ❌ | ❌ |
| Změnit jméno | ✅ | ✅ své firmy | ❌ | ❌ |
| Změnit roli | ✅ na `admin`/`manager`/`technician` | ✅ `manager` ↔ `technician` · ❌ na `admin` · ❌ jinému adminovi | ❌ | ❌ |
| Deaktivovat | ✅ | ✅ své firmy · ❌ jiného admina | ❌ | ❌ |
| Změnit/resetovat heslo | ✅ | ✅ uživatelům své firmy · ❌ jinému adminovi | ❌ | ❌ |
| Jakákoli změna superadmina | ❌ (403) | 🔒 (404) | ❌ | ❌ |
| Změna vlastní role, aktivace, hesla přes admin API | ❌ | ❌ | ❌ | ❌ |
| Vlastní heslo přes `POST /auth/change-password` | ✅ s ověřením současného hesla | ✅ | ✅ | ✅ |

**Při změně nebo resetu hesla jiným uživatelem a při deaktivaci:**
- nové heslo musí splnit stejnou politiku (`enforce_password_strength`),
- zvýší se `token_version` a revokují se všechny sessions a refresh tokeny cíle,
- operace se audituje fail-closed (bez zápisu do auditu se nic neuloží),
- heslo se nikdy neloguje.

### 2.1a Firemní správa uživatelů (`/api/v1/org/users*`, D-10)

Rozhodnutí D-10 z 17. 10. 2026: firemní admin spravuje uživatele své firmy z webu (zóna gateway) a desktopu (zóna desktop) přes `/org/users`. `/admin/users*` (2.1) je dostupné jen v zóně admin, tedy pro NovuAdmin přes WG.

| Operace | superadmin | admin (firma) | manager | technician |
|---|---|---|---|---|
| Seznam, detail | ❌ (403, systémová správa jde přes NovuAdmin) | ✅ jen své firmy · 🔒 cizí firma · 🔒 superadmin | ❌ | ❌ |
| Vytvořit | ❌ | ✅ role `manager`/`technician`, firma vždy vlastní (poslat `organizationId` → 422) · ❌ role `admin` (403) · `superadmin` (422) | ❌ | ❌ |
| Jméno, role `manager` ↔ `technician` | ❌ | ✅ své firmy · ❌ jinému adminovi a sobě (role) | ❌ | ❌ |
| Deaktivovat / znovu aktivovat | ❌ | ✅ své firmy · ❌ jiného admina · ❌ sebe | ❌ | ❌ |
| Reset hesla | ❌ | ✅ uživatelům své firmy · ❌ jinému adminovi · ❌ sobě | ❌ | ❌ |
| Impersonované tokeny | ❌ | ❌ | ❌ | ❌ |

Platí stejná pravidla jako v 2.1 (`app.core.rbac`): politika hesel, revokace sessions při resetu i deaktivaci, fail-closed audit akcí `org.user.create`, `org.user.patch` a `org.user.reset_password`. Firma má vždy aspoň jednoho admina, protože admin nemůže deaktivovat sebe ani jiného admina. Testy: `tests/test_d10_org_users.py`.

### 2.2 Správa firem (`/api/v1/admin/companies*`)

| Operace | superadmin | admin (firma) | manager | technician |
|---|---|---|---|---|
| Seznam firem | ✅ | ❌ | ❌ | ❌ |
| Založit firmu | ✅ | ❌ | ❌ | ❌ |
| Detail / úprava profilu firmy | ✅ libovolné | ✅ jen vlastní · 🔒 cizí | ❌ | ❌ |

### 2.3 Systémová administrace

| Operace | superadmin | admin | manager | technician |
|---|---|---|---|---|
| `/admin/jobs*` (výpis, retry, reprocess) | ✅ | ❌ | ❌ | ❌ |
| `/admin/logs`, `/admin/audit` | ✅ | ❌ | ❌ | ❌ |
| `/admin/impersonate/{id}` | ✅ (ne na superadmina) | ❌ | ❌ | ❌ |
| `/health/internal` | ✅ | ❌ | ❌ | ❌ |

### 2.4 Firemní data (zakázky, fotky, exporty, katalogy …)

| Operace | superadmin | admin | manager | technician |
|---|---|---|---|---|
| Čtení a běžná práce na datech své firmy | ✅ všech firem | ✅ | ✅ | ✅ |
| Manažerské operace (`require_manager`: workflow zakázky, PATCH zakázky, exporty, přepočet rozpočtu, SSE stream …) | ✅ | ✅ | ✅ | ❌ |
| Přístup k datům cizí firmy | ✅ | 🔒 | 🔒 | 🔒 |
| Přiřazení klienta zakázce nebo nabídce | ✅ jen klient firmy zakázky | ✅ jen klient vlastní firmy | ✅ jen klient vlastní firmy | — |

### 2.5 Firemní konfigurace, nabídky, exporty a fotky (SA-06, varianta A)

Schváleno 17. 10. 2026. Všechny operace navíc kontrolují firmu na backendu: cizí záznam vrací 🔒 404.

| Operace | Endpoint | superadmin | admin | manager | technician |
|---|---|---|---|---|---|
| Úprava materiálu (cena, výchozí dodavatel) | `PATCH /material-catalog/{id}` | ✅ | ✅ | ✅ | ❌ |
| Úprava dodavatele | `PATCH /suppliers/{id}` | ✅ | ✅ | ✅ | ❌ |
| Založení ceníku | `POST /pricebooks` | ✅ | ✅ | ✅ | ❌ |
| Nastavení typů prací pro firmu | `PUT /work-catalog/work-types/{code}/settings` | ✅ | ✅ | ✅ | ❌ |
| Schválení nabídky | `PATCH /offer-requests/{id}` | ✅ | ✅ | ✅ | ❌ |
| Nabídka s `auto_send` / `auto_review_bypass` | `POST /offer-requests` | ✅ | ✅ | ✅ | ❌ (bez příznaků ✅) |
| Zrušení, doplnění nabídky | `/offer-requests/{id}/cancel`, `/more-info` | ✅ | ✅ | ✅ | ✅ |
| Zrušení AI analýzy | `POST /analysis-jobs/{id}/cancel` | ✅ | ✅ | ✅ | ❌ |
| Detail / stažení exportu | `GET /exports/{id}` | ✅ | ✅ | ✅ | ❌ |
| Nahrání fotky, přesun, primární, referenční | `/cases/{id}/images*` | ✅ | ✅ | ✅ | ✅ |
| Měření, markery | `/measurements*`, `/markers*` | ✅ | ✅ | ✅ | ✅ |
| Smazání fotky (soft delete) | `DELETE /cases/{id}/images/{image_id}` | ✅ | ✅ | ✅ | ✅ jen vlastní (F0.3) |
| Koš a obnova fotky | `GET /cases/{id}/images/deleted`, `POST …/images/{image_id}/restore` | ✅ | ✅ | ✅ | ✅ jen vlastní (F0.3) |
| Trvalé smazání fotky | `POST /cases/{id}/images/{image_id}/purge` | ❌ → `POST /admin/photos/{id}/purge` | ✅ | ❌ | ❌ |
| Správa uživatelů a profilu firmy | `/admin/users*`, `/admin/companies/{id}` | ✅ | ✅ | ❌ | ❌ |

**Mazání fotek:** životní cyklus, vlastnictví (`uploaded_by_user_id`), trvalé smazání, chování při výpadku úložiště a zálohy jsou popsané v [PHOTO_DELETION.md](PHOTO_DELETION.md).

## 3. Databázové pojistky

| Constraint | Význam |
|---|---|
| `ck_users_role_valid` | `role IN ('superadmin','admin','manager','technician')` |
| `ck_users_superadmin_requires_flag` | `role <> 'superadmin' OR is_superadmin` |

## 4. Změny API kontraktu

| Endpoint | Před | Po |
|---|---|---|
| `POST /admin/users` | `role` libovolný řetězec, výchozí `dispatcher` | jen `admin`/`manager`/`technician`, výchozí `technician`; jinak 422 |
| `PATCH /admin/users/{id}` | neznámá pole se tiše ignorovala | neznámá pole → 422 |
| `POST/PATCH /admin/companies*`, `reset-password` | neznámá pole se ignorovala | neznámá pole → 422 |
| `GET/PATCH /admin/companies/{id}`, `/admin/users*` | jen superadmin (a omylem manager) | navíc firemní admin pro vlastní firmu |
| `PATCH /cases/{id}`, `POST /offer-requests` | cizí `clientId` se uložil | 400 `Client does not belong to this organization.` (stejně jako `POST /cases`) |
| `POST /auth/login`, `/refresh`, `/logout`, `/forgot-password`, `/reset-password` | rate limit podle neověřeného JWT | rate limit jen podle IP klienta |
| Endpointy v 2.5 označené ❌ pro technika | technik prošel | 403 `Manager access required.` |
| `DELETE /cases/{id}/images/{image_id}` | technik smazal, úložiště se vyčistilo do 30 s | jen manager/admin; obnova možná po dobu retence |
| `GET /cases/{id}/images/deleted`, `POST /cases/{id}/images/{image_id}/restore` | neexistovalo | nové (aditivní); technik jen vlastní fotky |
| `POST /cases/{id}/images/{image_id}/purge`, `POST /admin/photos/{photo_id}/purge` | neexistovalo | nové (aditivní), potvrzení `confirmImageId`, 200/202 |
| Výpadek Redisu u rate limitu (produkce) | — (počítadla v paměti procesu) | 503 (fail-closed), počítadla sdílená v Redisu |

Tvar odpovědí se nemění.
