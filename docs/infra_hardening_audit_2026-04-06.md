# Infra Hardening Audit - 2026-04-06

Rozsah: `docker-compose.yml`, `nginx/nginx.conf`, `python-backend/Dockerfile`,
`python-backend/docker-entrypoint.sh`, `python-backend/app/main.py`,
`python-backend/app/core/config.py`, `python-backend/app/core/limiter.py`,
`DEPLOY.md`, `OPERATIONS.md`, `RUNBOOK.md`, `RELEASE_CHECKLIST.md`.

Metoda: staticka analyza konfigurace + cileny beh:

`pytest python-backend/tests/test_config_production_hardening.py python-backend/tests/test_backend_smoke_guards.py python-backend/tests/test_csp_hardening.py python-backend/tests/test_auth_abuse_guards.py -q`

Vysledek behu:

- `124 passed`
- `1 failed`

Selhani ukazalo dalsi drift mezi docs/test expectation a aktualni readiness contract.

## Executive Summary

System je dnes `partially hardened`.

Silne stranky:

- DB, Redis a backend nejsou v `docker-compose.yml` publikovane primo na host.
- Verejny ingress je soustreden do `nginx`.
- `/api/v1/metrics` a `/api/v1/health/internal` jsou odriznute na nginx vrstve a `/metrics` ma navic bearer auth guard v aplikaci.
- Produkcni config ma realne fail-fast guardy na placeholder secrets, metrics auth, storage backend, CORS, APP_BASE_URL, worker metrics a debug mode.
- Rate limiting, queue backpressure a auth abuse guardy existuji.

Slabe stranky:

- chybi trusted proxy chain a trusted host guard
- kontejnery bezi bez least-privilege hardeningu
- vsechny sluzby sdileji jednu default Docker network a silne sdilene failure domains
- backend a worker sdileji stejne DB/Redis identity
- tajne hodnoty jsou predavane pres env vars, ne pres secret store
- `python-backend/docker-entrypoint.sh` stale automaticky spousti `alembic upgrade head`, coz je v rozporu s bezpecnym operacnim modelem deklarovanym v `DEPLOY.md`

Pro pilot je to provozne pouzitelne, ale blast radius po kompromitaci jedne aplikacni komponenty je stale prilis siroky.

## A) Sitova Expozice Sluzeb

### Stav

Dobry zaklad:

- `nginx` publikuje jen `80:80` a `443:443`
- `backend` nema `ports:`
- `db` nema `ports:`
- `redis` nema `ports:`
- `worker` nema host `ports:`, jen `expose: ${WORKER_METRICS_PORT}`

To znamena, ze z hostu nebo internetu nejsou DB, Redis ani backend v compose topologii primo otevrene.

### Rizika

`docker-compose.yml` nedefinuje oddelene site. Vse bezi na jedne default Docker network.

Dusledky:

- kompromitovany `backend` muze mluvit primo na `db`, `redis` i `worker`
- kompromitovany `worker` muze mluvit primo na `backend`, `db` i `redis`
- jakykoli dalsi kontejner pripojeny na stejnou sit ziska sitovy dosah na kriticke sluzby

Verdikt teto casti:

- host-level exposure: relativne dobre
- east-west isolation: slabe

## B) Oddeleni Verejnych a Internich Komponent

### Co je dobre

V `nginx/nginx.conf` je verejny a interni ingress oddelen:

- bezny traffic jde pres `location /`
- `/api/v1/metrics` je omezeny na localhost a RFC1918 rozsahy
- `/api/v1/health/internal` je omezeny stejne

App navic pro `/metrics` vynucuje:

- `METRICS_AUTH_ENABLED=true` v strict env
- bearer token
- volitelny `METRICS_IP_ALLOWLIST`

To je dobra defense-in-depth kombinace.

### Slabe misto

Interni/externi oddeleni je zavisle hlavne na:

- nginx ACL podle `remote_addr`
- jedine Docker network

Pokud bude pred nginx dalsi LB/reverse proxy, chybi:

- `set_real_ip_from`
- `real_ip_header`
- trusted proxy chain

Bez toho se IP-based guardy vyhodnocuji proti mezivrstve, ne proti skutecnemu klientovi.

## C) TLS, Headers, Proxy Chain, CORS, Ingress Guard

### Bezpecne casti

`nginx` ma rozumny TLS baseline:

- `ssl_protocols TLSv1.2 TLSv1.3`
- `ssl_session_tickets off`
- HSTS na 1 rok

Security headers existuji na obou vrstvach:

- nginx: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`
- app: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP

CORS je relativne dobre omezene:

- explicitni allowlist
- explicitni metody
- explicitni headery
- production validator odmitne localhost-only a placeholder origins

### Kriticke mezery

#### H1 [P0] Chybi trusted proxy chain

Backend bezi jako:

`uvicorn app.main:app --host 0.0.0.0 --port 8000`

Neni videt:

- `--proxy-headers`
- `--forwarded-allow-ips`
- `ProxyHeadersMiddleware`

Soucasne backend pouziva `request.client.host` pro:

- rate limiting fallback
- auth abuse logy
- security event logy
- `/metrics` IP allowlist

Dusledek:

- za reverse proxy muze app videt jen IP nginx/proxy vrstvy
- IP-based abuse guard muze byt nepresny nebo zbytecne sdileny
- audit a security eventy nemusi nest skutecnou klientskou IP

#### H2 [P1] Chybi trusted host guard

Neni videt `TrustedHostMiddleware` a nginx ma `server_name _`.

To znamena:

- neexistuje explicitni host-header allowlist
- ingress vrstva spoleha na topologii, ne na striktni host enforcement

Pro ciste API je to mensi riziko nez u server-side rendered app, ale pro hardening ingressu je to stale mezera.

#### H3 [P1] `REQUIRE_HTTPS=false` je bezpecne jen v konkretni topologii

V `.env.production.example` je `REQUIRE_HTTPS=false`.

To je rozumne jen proto, ze:

- TLS terminace probiha v nginx
- backend neni publikovan primo

Pokud by nekdo backend vystavil mimo tento compose profil, app sama HTTPS nevynuti. To neni bug v aktualni topologii, ale je to krehka zavislost na spravne ingress architekture.

## D) Least Privilege Pro Sluzby a Ucty

### Co je dobre

Produkce fail-fast odmitne:

- `APP_DEBUG=true`
- `DB_SEED_ON_STARTUP=true`
- placeholder `JWT_SECRET`
- placeholder `METRICS_AUTH_TOKEN`
- neautentizovany nebo slaboucky `REDIS_URL`
- `STORAGE_BACKEND=local` v strict env

To jsou dobre deployment defaults.

### Kriticke mezery

#### H4 [P0] Sluzby nemaji oddelene identity

V `docker-compose.yml`:

- backend a worker sdileji stejne `DATABASE_URL`
- backend a worker sdileji stejne `REDIS_URL`
- auth/cache/queue failure domain stale bezi na stejnem Redis endpointu

Dusledky:

- jedna kompromitovana app komponenta ma plny dosah na vsechen Redis runtime stav
- jedna kompromitovana app komponenta ma stejne DB opravneni jako druha
- blast radius mezi API plane a worker plane je siroky

#### H5 [P1] Chybi DB least privilege

Compose zaklada jeden Postgres user `novu` a ten je pouzity vsude.

Neni videt:

- read/write separation
- app vs worker DB role separation
- migration-only credential

To zhorsuje containment pri kompromitaci app procesu i bezpecnost operaci.

#### H6 [P1] Chybi secret store

Secrets jsou predavane pres env vars:

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `JWT_SECRET`
- `METRICS_AUTH_TOKEN`
- `ANTHROPIC_API_KEY`
- S3 credentials

Neni videt:

- Docker secrets
- vault/KMS integration
- oddeleny secret distribution path

To je bezne pro pilot, ale neni to hardening-grade reseni.

## E) Oddeleni Failure Domain a Blast Radius

### Co je dobre

- backend a worker jsou samostatne procesy/sluzby
- worker ma vlastni DB pool model
- nginx oddeluje verejny ingress od internich endpointu

### Kriticke mezery

#### H7 [P0] Vse bezi na single-host Compose stacku s jednou vnitrni siti

To znamena:

- zadna sitova segmentace mezi app, queue a DB vrstvou
- kompromitace jedne app komponenty vede k sirokemu lateral movementu
- chyba v `backend` nebo `worker` muze snadno prerust do plneho compromise `redis`/`db`

#### H8 [P1] Auth, cache a queue stale sdileji stejny Redis failure domain

To je uz driv zachyceno i v Redis auditu, ale z infra pohledu to porad plati:

- jeden Redis incident zasahuje vice provoznich roli
- jedna zneuzita aplikacni cesta ma dosah na vice druhu runtime stavu

#### H9 [P2] Worker metrics listener je interni, ale ne izolovany

`WORKER_METRICS_HOST=0.0.0.0` a `worker` expose-uje metrics port do Docker site.

Protoze neni publikovan na host, neni to verejny problem. Ale uvnitr jedine site je to stale dalsi intern endpoint, ktery je dostupny kazdemu peeru na teto siti.

## F) Ochrana Proti Pretizeni a Zneuziti

### Silne casti

- `slowapi` fail-fast guard v strict env
- rate limiting pro login, admin, upload, analysis jobs, list/detail read a metrics
- per-tenant/per-user limiter key pro autentizovane requesty
- account throttle pro auth
- queue backpressure a tenant job limity
- upload size limity
- S3 timeouty a signed URL TTL guardy

To je na pilot pomerne silny abuse baseline.

### Slabe casti

#### H10 [P1] IP-based ochrana je zavisla na neexistujicim trusted proxy nastaveni

Jakmile bude traffic chodit pres dalsi proxy vrstvu, per-IP guardy budou nepresne, protoze backend nepracuje s verifikovanym forwarded chain.

#### H11 [P2] Chybi host/container resource hardening

V `docker-compose.yml` neni videt:

- `mem_limit`
- `cpus`
- `pids_limit`
- `ulimits`
- `read_only`
- `tmpfs`

To zvetsuje sanci, ze jeden runaway proces zhorsuje stabilitu celeho hosta.

## G) Bezpecne Defaulty v Nasazeni

### Co je dobre

`python-backend/app/core/config.py` ma nadprumerne dobry strict runtime profil:

- vyzaduje explicitni runtime knobs v strict env
- odmitne placeholder secrets
- odmitne local storage v production
- odmitne placeholder APP_BASE_URL a CORS origins
- vyzaduje metrics auth
- vyzaduje worker metrics
- odmitne debug mode
- odmitne startup seed

To je silna cast celeho systemu.

### Kriticka mezera

#### H12 [P0] Backend entrypoint automaticky spousti migrace

`python-backend/docker-entrypoint.sh` dela:

`alembic upgrade head`

pak teprve startuje server.

To je v primem rozporu s `DEPLOY.md`, kde je deklarovano, ze migrace se maji spoustet explicitne a nikdy automaticky pri startu.

Dopady:

- restart backendu muze necekane mutovat schema
- zmena schema neni oddelena od startu aplikace
- rollback a change audit trail se zhorsuji
- bezpecne operace a blast radius DB zmen jsou horsi, nez dokumentace tvrdi

To je jeden z nejdulezitejsich P0 bodu celeho auditu.

## H) Host-Level a Container-Level Hardening

### Co je dobre

- certs jsou mountovane read-only
- nginx config je mountovany read-only
- DB/Redis nejsou publikovane primo na host

### Kriticke mezery

#### H13 [P0] Kontejnery nejsou zjevne rootless ani least-privilege

`python-backend/Dockerfile`:

- nepouziva ne-root user
- nema `USER`

`docker-compose.yml`:

- nema `user:`
- nema `read_only: true`
- nema `security_opt: no-new-privileges:true`
- nema `cap_drop`
- nema seccomp/apparmor profil

Dusledek:

- kompromitace app procesu ma zbytecne siroka opravneni v kontejneru
- containment na container vrstve je slabe

#### H14 [P2] Writable filesystem je siroky

Backend i worker maji writable root filesystem plus writable storage volume.

To samo o sobe neni chyba, ale bez dalsiho omezeni to zvetsuje post-exploitation prostor.

## I) Omezeni Primeho Pristupu ke Kritickym Sluzbam

### Co je dobre

- DB a Redis nejsou z hostu publikovane
- `/metrics` a `/health/internal` jsou na nginx omezeny na interne adresy
- `/metrics` ma bearer auth

### Co chybi

- interni service-to-service ACL
- oddelene Docker networks
- oddeleny admin plane
- oddeleny migration plane

Takze prime exposure z internetu je slusne omezeny, ale interni blast radius je stale velky.

## J) Auditovatelnost Zmen v Infrastrukture

### Co je dobre

- deployment, rollback, runbook a release checklist jsou zdokumentovane
- existuje `verify_release_gate.py`
- existuje backup/restore workflow
- app-level audit log existuje pro bezne security udalosti

### Slabe casti

#### H15 [P1] Infra zmeny nejsou samy o sobe auditovane

Neni videt:

- audit trail pro zmeny `.env.production`
- audit trail pro zmeny certifikatu
- audit trail pro zmeny nginx configu na hostu
- immutable deployment manifest/image pinning

`DEPLOY.md` stale pocita s:

`git pull origin main`

To je manualni a malo auditovatelny deploy pattern.

#### H16 [P2] Change path je dokumentacne nekonzistentni

Docs tvrdi explicitni migrace pred startem, ale image entrypoint dela automaticky upgrade.

To zhorsuje nejen safety, ale i auditovatelnost zmen, protoze operator nemusi presne vedet, kdy schema zmena probehla.

## Priority Fixu P0-P3

### P0

1. Odstranit automaticke `alembic upgrade head` z `python-backend/docker-entrypoint.sh` a vratit schema change jen do explicitniho release kroku.
2. Zavest trusted proxy chain:
   nginx `real_ip_header` / `set_real_ip_from` a backend proxy-header support.
3. Rozdelit Docker site minimalne na:
   `public` (nginx),
   `app-internal` (backend/worker),
   `data-internal` (db/redis).
4. Zavest container least privilege:
   non-root user, `read_only`, `no-new-privileges`, `cap_drop: [ALL]` tam kde je to mozne.
5. Oddelit identity:
   migration credential,
   app credential,
   worker credential,
   idealne i oddeleny auth/cache vs queue Redis plane.

### P1

1. Pridat `TrustedHostMiddleware` nebo ekvivalentni host allowlist.
2. Presunout secrets z env vars aspon do Docker secrets / host secret store.
3. Zprisnit internal metrics exposure:
   bud dedicated metrics network, nebo scrape sidecar/agent.
4. Zavest resource limity pro backend, worker, nginx.
5. Zmenit deploy z `git pull origin main` na image/tag/digest based release flow.

### P2

1. Zavest oddeleny admin/migration plane.
2. Zavest host-level firewall pravidla a explicitni operator docs pro interni metrics scraping.
3. Zlepsit infra change audit trail kolem env/config/certs.

### P3

1. Pridat dalsi defense-in-depth:
   mTLS mezi internimi komponentami, rootless Docker, seccomp/apparmor baseline.
2. Udelat periodicky hardening verification bundle jako soucast release gate.

## Verdikt

`partially hardened`

Interpretace:

- internet-facing exposure je rozumne stazene na nginx
- deployment config ma necekane silne fail-fast guardy
- ale vnitrni isolation, least privilege a safe operations discipline jeste nejsou na urovni maleho "contained blast radius" systemu

Nejvetsi blokery nejsou na hrane detailu. Jsou to zakladni veci:

- auto-migrace pri startu
- chybejici trusted proxy chain
- chybejici container least-privilege
- jedna default network a sdilene identity/failure domains

## Doporuceny kratky operator zaver

Pro pilot:

- pouzitelne, pokud stack zustane v presne teto topologii a na duveryhodnem hostu

Pro tvrdsi production profil:

- zatim ne

protoze kompromitace jedne aplikacni komponenty ma stale prilis siroky lateral movement a deployment change path neni dostatecne bezpecny ani auditovatelny.
