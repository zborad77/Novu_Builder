# NC-007 – Etapa 2: návrh databázových migrací (ke schválení)

| | |
|---|---|
| **Datum** | 22. 10. 2026 |
| **Stav** | **NÁVRH – čeká na schválení.** Nic z toho není implementováno ani migrováno. |
| **Důvod** | NC-007 vyžaduje MFA, pozvánky, ověření e-mailu, obnovu hesla a vynucenou změnu hesla. Bez nových sloupců a tabulek to nejde. Zadání zároveň říká „Neprovádět neodsouhlasené databázové migrace“. |
| **Navazuje na** | [NC-007_STAGE1_CONTRACT.md](NC-007_STAGE1_CONTRACT.md) · [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md) kap. 4.4 · [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) F5 |

## 1. Co jde bez migrace (nepotřebuje schválení)

| Věc | Kde se drží |
|---|---|
| Webové sessions | Redis gateway (etapa 1) |
| MFA login ticket (2 min) a throttle (5/ticket, 20/h/účet) | Redis core, klíče `nc:mfa:ticket:*`, `nc:mfa:fail:*` |
| Throttle obnovy hesla a pozvánek | Redis core (slowapi) |
| Tokeny obnovy hesla | **existující** tabulka `password_reset_tokens` (SHA-256, jednorázové, unikátní nepoužitý na uživatele) |
| Bezpečnostní audit | existující `audit_logs` |

## 2. Navržená migrace `20261023_0060_nc007_identity_security` (aditivní)

Všechny změny jsou aditivní a mají serverové výchozí hodnoty, takže migrace nezamyká provoz a dnešní kód s novým schématem běží beze změny (rollback kódu je bezpečný i bez downgradu).

### 2.1 `users` – nové sloupce

| Sloupec | Typ | Výchozí | Účel |
|---|---|---|---|
| `must_change_password` | boolean NOT NULL | `false` | vynucení změny po admin resetu: dokud je `true`, core povolí jen `/auth/me`, `/auth/change-password` a `/auth/logout` |
| `email_verified_at` | timestamptz NULL | – | ověření e-mailu (přijetím pozvánky) |
| `mfa_enabled_at` | timestamptz NULL | – | rychlý příznak „uživatel má aktivní TOTP“ |

### 2.2 `organizations` – politika MFA

| Sloupec | Typ | Výchozí | Hodnoty |
|---|---|---|---|
| `mfa_policy` | varchar(32) NOT NULL + CHECK | `'admins'` | `admins` (povinné pro `admin` a `manager`), `all` (povinné pro všechny). Firemní admin politiku jen zpřísní, povinnost pro adminy vypnout nejde (NC-007). |

### 2.3 Nové tabulky

**`user_mfa_totp`**

| Sloupec | Typ | Poznámka |
|---|---|---|
| `user_id` | PK, FK `users.id` ON DELETE CASCADE | jeden TOTP na uživatele |
| `secret_ciphertext` | bytea NOT NULL | AES-256-GCM, AAD = `user_id` |
| `key_id` | varchar(32) NOT NULL | id klíče z `MFA_ENCRYPTION_KEYS` (rotace) |
| `confirmed_at` | timestamptz NULL | `NULL` = rozpracovaná aktivace (nepočítá se jako MFA) |
| `last_used_step` | bigint NULL | ochrana proti opakovanému použití stejného kódu |
| `created_at` | timestamptz NOT NULL default now() | |

**`user_mfa_recovery_codes`**

| Sloupec | Typ | Poznámka |
|---|---|---|
| `id` | varchar(64) PK | |
| `user_id` | FK `users.id` ON DELETE CASCADE, index | |
| `code_hash` | varchar(128) NOT NULL | HMAC-SHA256 s pepřem `MFA_RECOVERY_PEPPER` (kódy mají ≥ 80 bitů entropie, proto stačí HMAC místo pomalého hashe) |
| `used_at` | timestamptz NULL | jednorázové |
| `created_at` | timestamptz NOT NULL default now() | |

Vygenerování nové sady starou sadu smaže (v jedné transakci).

**`user_invitations`**

| Sloupec | Typ | Poznámka |
|---|---|---|
| `id` | varchar(64) PK | |
| `organization_id` | FK `organizations.id` ON DELETE CASCADE, index | pozvánka je vždy do firmy pozývajícího |
| `email` | varchar(255) NOT NULL | normalizovaný na malá písmena |
| `role` | varchar(64) NOT NULL + CHECK (`manager`, `technician`) | firemní admin nesmí pozvat `admin` ani `superadmin` (D-10) |
| `token_hash` | varchar(128) UNIQUE NOT NULL | SHA-256, surový token jen v e-mailu |
| `invited_by_user_id` | FK `users.id` ON DELETE SET NULL | |
| `expires_at` | timestamptz NOT NULL | výchozí 72 h |
| `accepted_at`, `revoked_at` | timestamptz NULL | |
| `created_at` | timestamptz NOT NULL default now() | |
| index | UNIQUE (`organization_id`, `email`) WHERE `accepted_at IS NULL AND revoked_at IS NULL` | jedna aktivní pozvánka na e-mail a firmu |

Ověření e-mailu = přijetí pozvánky (odkaz z e-mailu prokazuje vlastnictví adresy). Samostatná tabulka pro ověřovací tokeny proto není potřeba. Změna e-mailu uživatelem je mimo rozsah NC-007.

### 2.4 `user_sessions` – nové sloupce

| Sloupec | Typ | Účel |
|---|---|---|
| `mfa_verified_at` | timestamptz NULL | session vznikla s druhým faktorem |
| `reauthenticated_at` | timestamptz NULL | re-autentizace pro citlivé operace (platí 5 min) |

## 3. Nové endpointy core (aditivní, zóny podle exposure matrix kap. 11)

| Metoda | Cesta | Zóna | Poznámka |
|---|---|---|---|
| POST | `/api/v1/auth/login/start` | G, A (D viz otázka R4) | vrací `{mfaRequired, mfaEnrollmentRequired, ticket}` nebo tokeny |
| POST | `/api/v1/auth/login/mfa` | G, A | TOTP nebo recovery kód + ticket |
| GET/POST/DELETE | `/api/v1/auth/mfa/totp` | G, D, A | stav, aktivace (secret + `otpauth://` URI jen jednou), potvrzení, vypnutí (re-auth; adminům vypnutí nejde, když je MFA povinné) |
| POST | `/api/v1/auth/mfa/recovery-codes` | G, D, A | nová sada (re-auth), kódy se vrátí jen jednou |
| POST | `/api/v1/auth/reauth` | G, D, A | heslo (+ TOTP, když ho uživatel má) → `reauthenticated_at` |
| GET/POST/DELETE | `/api/v1/org/invitations` | G, D | firemní admin, jen vlastní firma |
| POST | `/api/v1/auth/invitations/accept` | G | veřejné: token + heslo + jméno → účet s `email_verified_at` |
| POST | `/api/v1/auth/forgot-password` | G | dnes 410 → vždy 202, anti-enumerace, IP 5/h, e-mail 3/h |
| POST | `/api/v1/auth/reset-password` | G | jednorázový token 30 min, revokace všech sessions |

`POST /auth/login` se nemění. Admin reset hesla (`/org/users/{id}/reset-password`) nově nastaví `must_change_password = true`.

Samoregistrace nové firmy zůstává blokovaná. Pozvánka vždy vytvoří uživatele jen v existující firmě pozývajícího.

## 4. Nové secrets (systemd `LoadCredential`, jen core)

`MFA_ENCRYPTION_KEYS` (`kid:base64(32 B)[,…]`), `MFA_RECOVERY_PEPPER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS_MODE`. Mimo development chybějící hodnota = proces nenastartuje. Pro testy je explicitní adaptér `EMAIL_BACKEND=memory`, který je mimo `test`/`development` zakázaný (žádný skrytý fallback).

## 5. Rozhodnutí potřebná od zadavatele

| ID | Otázka | Doporučení |
|---|---|---|
| **R1** | Schválit migraci 0060 v rozsahu kap. 2? | Ano |
| **R2** | Stávající uživatelé a `email_verified_at`: (a) v migraci nastavit `email_verified_at = created_at` (účty zakládal admin, řízená datová změna, zdokumentovaná a vratná), nebo (b) nechat `NULL` a ověření vymáhat jen u nových účtů z pozvánky | (a) |
| **R3** | D-05: zapnout obnovu hesla e-mailem (vyžaduje SMTP účet a odchozí pravidlo nftables na SMTP) | Ano, až bude SMTP účet |
| **R4** | Desktop a MFA: dnešní desktop umí jen `POST /auth/login`. Buď (a) uživatel s aktivním MFA se v desktopu nepřihlásí, dokud desktop nepodporuje `/auth/login/start` (F7), nebo (b) desktop dočasně bez MFA (zóna je za WG a s device binding) | (a) pro firemní adminy, (b) pro ostatní do F7 |
| **R5** | Výchozí `mfa_policy` pro existující firmy `admins` (povinné MFA pro `admin` i `manager`), nebo jen pro `admin` | `admins` podle SECURITY_ARCHITECTURE 4.4 |
