# NovuConstruct – API Exposure Matrix

| | |
|---|---|
| **Datum** | 17. 10. 2026 |
| **Stav** | **NÁVRH ke schválení.** Zóny zatím neexistují (SA-26). Sloupec „Dnes“ popisuje skutečný stav k `904ac05`. |
| **Zdroj** | Inventář vygenerovaný importem `app.main:app` a průchodem `route.dependant.dependencies`: 113 rout, z toho 108 pod `/api/v1`. |
| **Související** | [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 3 · [SECURITY_AUDIT.md](SECURITY_AUDIT.md) |

## Stav implementace (17. 10. 2026)

Zóny jsou implementované ve větvi `fix/f0-rbac-tenant-isolation` (F3.1–F3.3, F3.5), **zatím nenasazené**.

- **Zdroj pravdy je kód:** [`src/backend/app/platform/http/exposure.py`](../../src/backend/app/platform/http/exposure.py). Tato tabulka ho popisuje.
- **Zóna se určuje jen z procesu:** `NC_ZONE` v `deploy/linux/systemd/nc-api@.service`.
- **Nezařazená route** je blokovaná ve všech produkčních zónách, i v admin.
- **Odchylky od původního návrhu:**
  - `GET /api/v1/health` je navíc v zóně D, protože ho volá desktop při nastavení serveru,
  - `POST /api/v1/offer-requests/{offer_id}/more-info` je v zónách G/D,
  - routy z F0.3 (koš, obnova a trvalé smazání fotek, `/admin/photos/{id}/purge`) odpovídají tabulce v kap. 5 a 10.
- **Allowlist pro gateway** je generovaný soubor [gateway-allowlist.json](gateway-allowlist.json) (91 rout). Hlídá ho test `tests/test_gateway_allowlist.py`.
- **JWT** nese `aud` podle zóny (`nc-web`, `nc-desktop`, `nc-admin`), dále `iss` a `iat`. Token z jiné zóny vrací 401. Superadmin se přihlásí jen v zóně A.

## Legenda

| Zóna | Význam |
|---|---|
| **P** | Veřejné (internet). **Jen endpointy gateway `/bff/*`.** Core nemá žádnou veřejnou routu. |
| **G** | Zóna `gateway`: core je dosažitelné jen z WG peeru gateway, operace jsou v allowlistu BFF. |
| **D** | Zóna `desktop`: enrollované desktopové peery přes WG. |
| **A** | Zóna `admin`: peery NovuAdminu a monitoring přes `wg-nc-admin`. |
| **DEV** | Jen `APP_ENV=development`, v produkci se nemontuje. |
| **—** | Nikde. |

Mimo povolenou zónu vrací route **404**, ne 403.

| Role | Význam |
|---|---|
| **any** | libovolný přihlášený uživatel v rámci své firmy |
| **mgr** | `manager` (nebo `superadmin`, ten se ale v G/D nepřihlásí) |
| **sa** | jen `superadmin` |

V tabulkách: ⚠ = změna role nebo kontroly oproti dnešku, viz uvedený nález. **Tučně** = zásadní změna.

---

## 1. Veřejné endpointy gateway (P)

Implementuje je `nc-gateway` a core je nevystavuje. Toto je **úplný seznam** veřejného útočného povrchu.

| Metoda | Cesta (edge) | Volá na core (zóna G) | Proč musí být veřejný | Ochrana |
|---|---|---|---|---|
| GET | `/` a statické soubory SPA | – | webové UI | CSP, immutable cache |
| GET | `/bff/health` | – | externí uptime monitoring | vrací jen `{"status":"ok"}`, nic o core |
| POST | `/bff/auth/login` | `/auth/login` → později `/auth/login/start` | přihlášení | IP 20/5 min, účet 10 neúsp./15 min s progresivním zpožděním, jednotná 401 |
| POST | `/bff/auth/mfa` | `/auth/login/mfa` (NEW) | druhý faktor | ticket 2 min, 5 pokusů na ticket |
| POST | `/bff/auth/logout` | `/auth/logout` | odhlášení nesmí být těžší než přihlášení | CSRF |
| GET | `/bff/session` | `/auth/me` | stav session + `csrfToken` | jen s platnou cookie |
| POST | `/bff/auth/forgot` | `/auth/forgot-password` | obnova hesla (**jen po D-05**, dnes 410) | vždy 202, IP 5/h, e-mail 3/h |
| POST | `/bff/auth/reset` | `/auth/reset-password` | dokončení obnovy (**jen po D-05**) | jednorázový token 30 min, revokace sessions |
| POST | `/bff/device-enrollment` | `/devices/enroll` (NEW) | zařízení bez WG se musí zaregistrovat (D-07) | kód 128 bit, 24 h, jednorázový, vyžaduje schválení |
| * | `/bff/api/<allowlist>` | odpovídající `/api/v1/...` | operace webového UI | session + CSRF + allowlist (sekce 2–9, sloupec G) |

Vše ostatní na edge vrací 404: `/api/*`, `/docs`, `/openapi.json`, `/metrics`, `/admin`.

---

## 2. Systém a provoz

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/` | veřejné, vrací `APP_ENV` | A | – | SA-24 |
| GET | `/api/v1/alive` | veřejné | A | – | liveness pro monitoring |
| GET | `/api/v1/health` | veřejné, spouští kontroly DB, Redis, úložiště | A | – | externí monitoring používá `/bff/health` |
| GET | `/api/v1/ready` | veřejné | A | – | |
| GET | `/api/v1/ready/processing` | veřejné | A | – | |
| GET | `/api/v1/health/internal` | sa | A | sa | |
| GET | `/api/v1/metrics` | token + volitelný allowlist IP | A | token | jen monitoring peer |
| GET | `/openapi.json` | **veřejné i v produkci** | DEV | – | SA-17 |
| GET | `/docs`, `/docs/oauth2-redirect`, `/redoc` | jen při debug | DEV | – | |
| GET | `/mock-storage/{file_path:path}` | dev, autentizace | DEV | any | SA-09, opravit traversal |

## 3. Autentizace

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/login` | veřejné | G, D, A | – | V G a A jen do zavedení MFA (pak `/auth/login/start`). Superadmin jen v A. ⚠ SA-03: klíč limitu jen IP. |
| POST | `/api/v1/auth/refresh` | veřejné | G, D, A | – | ⚠ SA-10: reuse zruší celou session. Token platí jen ve své zóně (`aud`). |
| POST | `/api/v1/auth/logout` | veřejné | G, D, A | – | |
| POST | `/api/v1/auth/forgot-password` | veřejné, 410 | G (po D-05) | – | |
| POST | `/api/v1/auth/reset-password` | veřejné, 410 | G (po D-05) | – | |
| GET | `/api/v1/auth/me` | any | G, D, A | any | |
| POST | `/api/v1/auth/change-password` | any | G, D, A | any | ⚠ nepoužívat `service.login` k ověření (vytváří session) |
| GET | `/api/v1/auth/sessions` | any | G, D, A | any | |
| DELETE | `/api/v1/auth/sessions/{session_id}` | any | G, D, A | any | ⚠ SA-15: zakázat pro impersonovaný token |

## 4. Zakázky a workflow

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/cases` | any | G, D | any | |
| POST | `/api/v1/cases` | any | G, D | any | |
| GET | `/api/v1/cases/{case_id}` | any | G, D | any | |
| PATCH | `/api/v1/cases/{case_id}` | mgr | G, D | mgr | ⚠ **SA-02: ověřit `clientId` ve firmě** |
| POST | `/api/v1/cases/{case_id}/duplicate` | mgr | G, D | mgr | |
| GET | `/api/v1/cases/{case_id}/timeline` | any | G, D | any | |
| GET | `/api/v1/cases/{case_id}/activity/stream` (SSE) | mgr | G, D | mgr | ⚠ SA-12: re-auth, limity spojení |
| POST | `/api/v1/cases/{case_id}/submit` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/start-analysis` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/approve-proposal` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/send` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/return-to-draft` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/cancel` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/archive` | mgr | G, D | mgr | |
| PATCH | `/api/v1/cases/{case_id}/proposal-draft` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/final-proposal` | mgr | G, D | mgr | |

## 5. Fotky, měření, markery

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/cases/{case_id}/images` | any | G, D | any | `previewUrl` → streamovací endpoint (kap. 10) |
| POST | `/api/v1/cases/{case_id}/images` | any | G, D | any | ⚠ SA-11: limit souborů, validace v threadu. Gateway: tělo 25 MB. |
| DELETE | `/api/v1/cases/{case_id}/images/{image_id}` | any | G, D | any | rozhodnout, jestli mgr |
| PATCH | `/api/v1/cases/{case_id}/images/{image_id}/analysis-reference` | any | G, D | any | |
| PATCH | `/api/v1/cases/{case_id}/images/{image_id}/move` | any | G, D | any | |
| PATCH | `/api/v1/cases/{case_id}/images/{image_id}/primary` | any | G, D | any | |
| GET | `/api/v1/images/{image_id}/preview` | any | G, D | any | dnes redirect na presigned URL, cíl streamování (SA-16) |
| POST | `/api/v1/cases/{case_id}/measurements` | any | G, D | any | ⚠ **SA-08: `referenceImageId` v rámci zakázky + kontrola zámku** |
| PATCH | `/api/v1/measurements/{measurement_id}` | any | G, D | any | |
| POST | `/api/v1/measurements/{measurement_id}/confirm` | any | G, D | any | |
| GET | `/api/v1/markers` | any | G, D | any | doplnit cross-tenant test |
| POST | `/api/v1/markers` | any | G, D | any | doplnit cross-tenant test (cizí `imageId`) |
| DELETE | `/api/v1/markers/{marker_id}` | any | G, D | any | |

## 6. Analýza (AI)

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/cases/{case_id}/analysis-jobs` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/analysis-jobs` | any | G, D | any | ⚠ zvážit mgr (spotřebovává AI budget) |
| GET | `/api/v1/analysis-jobs/{job_id}` | any | G, D | any | |
| POST | `/api/v1/analysis-jobs/{job_id}/cancel` | any | G, D | **mgr** | ⚠ SA-06 |
| POST | `/api/v1/analysis-jobs/{job_id}/retry` | mgr | G, D | mgr | |
| PATCH | `/api/v1/cases/{case_id}/analysis-results/{result_id}/selection` | mgr | G, D | mgr | ⚠ SA-23: validace a limit `polygon` |

## 7. Položky prací, rozpočty, exporty

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/cases/{case_id}/work-items` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/work-items` | any | G, D | any | |
| GET | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}/detections` | any | G, D | any | ⚠ SA-23: `analysisJobId` |
| PATCH | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values` | any | G, D | any | |
| PUT | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values/confirm` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/work-items/{project_work_item_id}/values/merge` | any | G, D | any | |
| GET | `/api/v1/cases/{case_id}/work-types/{work_type_code}/effective-configuration` | any | G, D | any | |
| GET | `/api/v1/cases/{case_id}/estimates` | any | G, D | any | |
| POST | `/api/v1/cases/{case_id}/estimates/recalculate` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/exports/case-zip` | mgr | G, D | mgr | ⚠ SA-22: originály s EXIF |
| POST | `/api/v1/cases/{case_id}/exports/proposal-docx` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/exports/quote-docx` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/exports/quote-pdf` | mgr | G, D | mgr | |
| POST | `/api/v1/cases/{case_id}/exports/report-pdf` | mgr | G, D | mgr | |
| GET | `/api/v1/exports/{export_id}` | any | G, D | **mgr** | ⚠ SA-06. `downloadUrl` → streamovací endpoint, audit stažení (SA-14). |

## 8. Katalogy, ceníky, dodavatelé

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/work-catalog/catalog/categories` | any | G, D | any | |
| GET | `/api/v1/work-catalog/catalog/grouped` | any | G, D | any | |
| GET | `/api/v1/work-catalog/catalog/work-types` | any | G, D | any | |
| GET | `/api/v1/work-catalog/catalog/work-types/{work_type_code}` | any | G, D | any | |
| GET | `/api/v1/work-catalog/catalog/work-types/{work_type_code}/parameters/{parameter_code}` | any | G, D | any | |
| GET | `/api/v1/work-catalog/work-types` | any | G, D | any | |
| GET | `/api/v1/work-catalog/work-types/{work_type_code}/effective` | any | G, D | any | |
| PUT | `/api/v1/work-catalog/work-types/{work_type_code}/settings` | any | G, D | **mgr** | ⚠ SA-06 |
| GET | `/api/v1/material-catalog` | any | G, D | any | |
| PATCH | `/api/v1/material-catalog/{material_id}` | any | G, D | **mgr** | ⚠ SA-06, **SA-07: `defaultSupplierId` ve firmě** |
| GET | `/api/v1/material-catalog/{material_id}/supplier-prices` | any | G, D | any | |
| GET | `/api/v1/pricebooks` | any | G, D | any | |
| POST | `/api/v1/pricebooks` | any | G, D | **mgr** | ⚠ SA-06 |
| GET | `/api/v1/pricebooks/{pricebook_id}/items` | any | G, D | any | |
| GET | `/api/v1/suppliers` | any | G, D | any | |
| PATCH | `/api/v1/suppliers/{supplier_id}` | any | G, D | **mgr** | ⚠ SA-06; validovat schéma `websiteUrl` |

## 9. Nabídky (offer pipeline)

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| POST | `/api/v1/offer-requests` | any | G, D | any | ⚠ SA-06: `auto_review_bypass`/`auto_send` jen pro mgr. Limit `photo_ids`. |
| GET | `/api/v1/offer-requests/{offer_id}` | any | G, D | any | |
| PATCH | `/api/v1/offer-requests/{offer_id}` (approve) | any | G, D | **mgr** | ⚠ SA-06 |
| POST | `/api/v1/offer-requests/{offer_id}/cancel` | any | G, D | any | |
| POST | `/api/v1/offer-requests/{offer_id}/more-info` | any | G, D | any | |
| GET | `/api/v1/offer-requests/{offer_id}/result` | any | G, D | any | |
| GET | `/api/v1/offer-requests/{offer_id}/status` | any | G, D | any | |
| GET | `/api/v1/offer-requests/{offer_id}/events` (SSE) | any | G, D | any | ⚠ SA-12 |

## 10. Administrace

**Aktualizace F0 (17. 10. 2026):** systémové routy (`/admin/companies` výpis a založení, `/admin/jobs*`, `/admin/logs`, `/admin/audit`, `/admin/impersonate`) jsou jen pro `sa`. Správa uživatelů (`/admin/users*`) a profil vlastní firmy (`GET/PATCH /admin/companies/{id}`) jsou nově dostupné i firemnímu adminovi (role `admin`), a to jen v rámci jeho firmy. Pravidla jsou v [RBAC_ROLE_MATRIX.md](RBAC_ROLE_MATRIX.md). **Rozhodnutí D-10 (17. 10. 2026):** firemní admin spravuje uživatele své firmy přes nové tenant-scoped `/org/users` v zónách G a D (tabulka níže). Celé `/admin/*` zůstává jen v zóně A pro NovuAdmin přes WG, gateway z něj neodkrývá nic.

| Metoda | Cesta | Zóna | Role | Poznámka |
|---|---|---|---|---|
| GET | `/api/v1/org/users` | G, D | admin (firma) | jen uživatelé vlastní firmy, superadmini neviditelní |
| POST | `/api/v1/org/users` | G, D | admin (firma) | firma = firma admina (pole `organizationId` → 422), role jen `manager`/`technician` |
| GET | `/api/v1/org/users/{user_id}` | G, D | admin (firma) | cizí firma / superadmin → 404 |
| PATCH | `/api/v1/org/users/{user_id}` | G, D | admin (firma) | jméno, role, aktivace; deaktivace odvolá sessions; jiný admin a vlastní účet → 403 |
| POST | `/api/v1/org/users/{user_id}/reset-password` | G, D | admin (firma) | nové heslo dle politiky, odvolá sessions; jiný admin → 403 |

| Metoda | Cesta | Dnes | Zóna | Role | Poznámka |
|---|---|---|---|---|---|
| GET | `/api/v1/admin/companies` | sa | A | sa | |
| POST | `/api/v1/admin/companies` | **admin:write (i manager)** | A | **sa** | ⚠ **SA-01** |
| GET | `/api/v1/admin/companies/{company_id}` | sa | A | sa | |
| PATCH | `/api/v1/admin/companies/{company_id}` | **admin:write (i manager)** | A | **sa** | ⚠ **SA-01** |
| GET | `/api/v1/admin/users` | sa | A | sa | ⚠ SA-14: auditovat čtení |
| POST | `/api/v1/admin/users` | **admin:write (i manager)** | A | **sa** | ⚠ **SA-01**: enum rolí |
| GET | `/api/v1/admin/users/{user_id}` | sa | A | sa | |
| PATCH | `/api/v1/admin/users/{user_id}` | **admin:write (i manager)** | A | **sa** | ⚠ **SA-01, SA-04** |
| POST | `/api/v1/admin/users/{user_id}/reset-password` | **admin:write (i manager)** | A | **sa** | ⚠ **SA-01** |
| GET | `/api/v1/admin/jobs` | admin:jobs | A | sa | |
| GET | `/api/v1/admin/jobs/{job_id}` | admin:jobs | A | sa | |
| POST | `/api/v1/admin/jobs/{job_id}/retry` | admin:jobs | A | sa | |
| POST | `/api/v1/admin/jobs/{job_id}/reprocess` | admin:jobs | A | sa | |
| GET | `/api/v1/admin/logs` | sa | A | sa | |
| GET | `/api/v1/admin/audit` | sa | A | sa | NEW filtry (kap. 11) |
| POST | `/api/v1/admin/impersonate/{user_id}` | admin:impersonate | A | sa + MFA | ⚠ SA-15: token `aud=nc-web`, `sid`, revokovatelný |

---

## 11. Nové endpointy (aditivní, návrh)

Žádný stávající kontrakt se nemění.

| Metoda | Cesta | Zóna | Role | Účel | Fáze |
|---|---|---|---|---|---|
| POST | `/api/v1/auth/login/start` | G, A (později D) | – | přihlášení, krok 1, vrací `mfaRequired` + ticket | F5 |
| POST | `/api/v1/auth/login/mfa` | G, A (později D) | – | krok 2 (TOTP nebo recovery kód) | F5 |
| GET/POST/DELETE | `/api/v1/auth/mfa/totp` | G, D, A | any | aktivace a deaktivace TOTP (re-auth heslem) | F5 |
| POST | `/api/v1/auth/mfa/recovery-codes` | G, D, A | any | nové recovery kódy | F5 |
| GET | `/api/v1/files/images/{image_id}/{variant}` | G, D | any | streamování náhledu nebo originálu (D-03) | F4 |
| GET | `/api/v1/files/exports/{export_id}` | G, D | mgr | streamování exportu + audit | F4 |
| POST | `/api/v1/devices/enroll` | G | – (enrollment kód) | registrace veřejného WG klíče zařízení (D-07) | F6 |
| GET/DELETE | `/api/v1/admin/users/{user_id}/sessions` | A | sa | sessions uživatele | F7 |
| GET/POST/DELETE | `/api/v1/admin/devices` | A | sa | správa WG peerů | F6 |
| GET | `/api/v1/admin/system/overview` | A | sa | verze, migrace, fronta, úložiště, certifikáty | F7 |
| POST | `/api/v1/admin/security/revoke-all-web-sessions` | A | sa + MFA | runbook při kompromitaci gateway | F7 |
| POST | `/api/v1/internal/security-events` | G | HMAC gateway | zápis bezpečnostních událostí z gateway do `audit_logs` | F4 |

---

## 12. Souhrn

| Zóna | Počet rout (stávající) |
|---|---|
| P (core) | **0** |
| G | 77 business + 7 auth = 84 (+2 po D-05) |
| D | 77 business + 7 auth = 84 |
| A | 15 admin + 7 systém + 7 auth = 29 |
| DEV | 5 |

Allowlist gateway je **podmnožina zóny G**. Vznikne z tabulky výše a generuje se do [`docs/security/gateway-allowlist.json`](gateway-allowlist.json) z `app/platform/http/exposure.py` (`python -m scripts.export_gateway_allowlist`). Test v CI kontroluje, že gateway nepustí nic mimo zónu G a že allowlist neobsahuje žádnou `/admin` routu.
