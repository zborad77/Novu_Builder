# NovuConstruct – Matice rolí a oprávnění (RBAC)

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | Implementováno ve větvi `fix/f0-rbac-tenant-isolation` (F0), **zatím nevydáno**. |
| **Zdroj pravdy v kódu** | [`app/core/rbac.py`](../../python-backend/app/core/rbac.py), závislosti v [`app/api/deps.py`](../../python-backend/app/api/deps.py), migrace `20261017_0057` |
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
- Impersonační token se do žádné administrace nedostane (403).

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

Doplnění chybějících kontrol rolí u zápisů do katalogů, ceníků a schvalování nabídek (SA-06) je samostatný úkol F2.1 v [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

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

Tvar odpovědí se nemění.
