# NOVU Builder

## Prezentační a obchodní dokument — verze 1.0

**Verze systému:** v0.7.001  
**Datum dokumentu:** 2. dubna 2026  
**Určeno pro:** potenciální investory, obchodní partnery, pilotní zákazníky

---

## 1. Úvod a positioning projektu

### Co je NOVU Builder

NOVU Builder je software pro automatizované zpracování stavebních nabídek a cenových odhadů. Jde o backend-first systém s vícevrstvou architekturou, který propojuje sběr dat v terénu, AI analýzu fotografií a řízenou tvorbu cenových podkladů.

Základní pracovní tok: technik pořídí fotodokumentaci stavebního objektu nebo škody, data jsou odeslána do systému, AI pipeline analyzuje snímky vůči katalogu 43 stavebních prací a generuje strukturovaný návrh cenové nabídky. Výstup přebírá pracovník v kanceláři, upraví ho a odešle zákazníkovi.

Systém je navržen jako multi-tenant SaaS — každá firma (tenant) pracuje ve striktně izolovaném datovém prostoru se svými projekty, zakázkami a nastavením.

### Jaký problém řeší

Zpracování cenových nabídek ve stavebnictví je časově náročné, chybovité a silně závislé na zkušenosti konkrétního odhadce. Standardní postup zahrnuje ruční procházení fotodokumentace, manuální výběr položek z ceníku a ruční kalkulaci. Čas od návštěvy objektu po odeslanou nabídku se typicky pohybuje v řádu hodin až dnů.

NOVU Builder tento proces strukturuje: vstup je standardizovaný (foto + kontext), zpracování je řízené a auditovatelné, výstup je parametrizovaný a editovatelný. Cílem není nahradit odborného pracovníka, ale výrazně zkrátit čas, který stráví rutinní prací.

### Pro koho je určen

Primárním uživatelem jsou firmy a živnostníci, kteří provádějí opravy, rekonstrukce nebo stavební práce a potřebují opakovaně generovat cenové nabídky na základě terénní obhlídky. Systém je dimenzován pro provoz s desítkami až stovkami tenantů.

Uživatelé se dělí na tři role:

- **Technici v terénu** — pracují přes mobilní aplikaci, pořizují dokumentaci a odesílají zakázky
- **Kancelářský personál** — pracuje přes desktopovou Qt6 aplikaci, reviduje AI výstupy, upravuje nabídky a odesílá je zákazníkům
- **Správci systému (superadmin)** — spravují tenanty, uživatele a provozní konfiguraci

### Proč je přínosný oproti běžným řešením

Dostupné nástroje pro tvorbu stavebních nabídek jsou zpravidla buď obecné (tabulkové procesory, fakturační software), nebo silně oborově specifické s uzavřenou architekturou. Žádný z nich nativně propojuje terénní sběr fotografií, AI analýzu a katalogem řízenou kalkulaci v jednom řízeném toku.

NOVU Builder přináší specificky:

- Strukturovaný katalog 43 stavebních prací s parametrizovanými vstupy a vazbou na AI extrakci
- Oddělení terénního sběru dat od kancelářského zpracování
- Verzované analytické a cenové profily, které umožňují sledovat, jak se nabídka vyvíjela
- Auditovatelné zpracování — každá změna a každý stav mají zaznamenaný kontext

---

## 2. Hlavní provozní flow systému

### Vstup dat

Technik v terénu spouští zakázku přes mobilní aplikaci: zaznamená základní informace o objektu, pořídí fotodokumentaci a odešle data do systému. Na backend přicházejí fotografie jako strukturovaný upload se stavovým řízením — každý soubor prochází validací formátu, velikosti a bezpečnostní kontrolou před uložením do storage backendu.

Paralelně může zakázku vytvořit kancelářský pracovník přes desktopovou aplikaci — oba způsoby produkují identickou datovou strukturu.

### Zpracování — AI analýza

Po vytvoření zakázky a nahrání fotografií je možné spustit analýzu. Systém zařadí úlohu do Redis-backed fronty s řízenou prioritou a kapacitními limity. Worker process úlohu vyzvedne, zajistí si exkluzivní `lease` (časový zámek s vlastnickým tokenem) a spustí AI pipeline.

Pipeline probíhá ve třech fázích s explicitními datovými kontrakty:

1. **Detection** — AI provider (Anthropic Claude nebo jiný nakonfigurovaný) identifikuje typ objektu (střecha, fasáda, interiér, základ), stav povrchu (dobrý, vyžaduje pozornost, kritický), výměru a souřadnice oblasti v obrazu. Výsledek je `DetectionStageResult` — immutable datová struktura s confidence score.

2. **Extraction** — Z detekce se extrahují strukturované veličiny: odhadovaná plocha v m², primární měrná jednotka, doporučený rozsah opravy (čištění / lokální oprava / plná rekonstrukce), seznam materiálů s orientačními cenami a přehled pracovních kroků s odhadem hodin. Výsledek je `ExtractionStageResult`.

3. **Work Catalog Mapping** — Extrahované veličiny jsou namapovány na konkrétní položku v katalogu prací (jeden ze 43 typů), přiřazen analytický profil a validovány vůči pravidlům pro daný typ práce. Výsledek je `WorkCatalogMappingResult` s primární hodnotou, jednotkou a případnými validačními varováními.

Všechny tři výstupy jsou agregovány do `PipelineRunResult`, který putuje do databáze jako vstup pro cenovou kalkulaci.

### Výstup — cenová nabídka

Na základě výsledků AI pipeline systém vytvoří návrh cenové nabídky s položkami odvozenými z katalogových ceníkových profilů (43 profilů, každý s pravidly pro materiály, práci a úpravami). Kancelářský pracovník návrh přebírá v desktopové aplikaci, upravuje množství a ceny, přidává nebo odebírá položky a odesílá finální nabídku zákazníkovi.

### Role jednotlivých částí systému

| Komponenta                | Role                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| **FastAPI backend**       | REST API — auth, správa projektů, zakázek, analýz, exportů; validace vstupů; rate limiting |
| **Redis**                 | Fronta analytických úloh, cache katalogů a tenantských nastavení, throttle pro autentizaci |
| **Worker process**        | Asynchronní zpracování analýz; izolovaný od API procesu; vlastní DB pool; lease model      |
| **PostgreSQL**            | Primární úložiště všech dat; 40 schematicky verzovaných migrací                            |
| **S3-compatible storage** | Uložiště fotografií a exportů; přístup pouze přes podepsané URL s TTL                      |
| **Nginx**                 | Reverzní proxy, HTTPS terminace, první linie rate limitingu                                |

---

## 3. Produkční logika

### Systém není demo — je navržen pro řízený provoz

Architektonická rozhodnutí v NOVU Builderu jsou konzistentně zaměřena na produkční provoz, ne na rychlou funkčnost prototypu. To se projevuje na několika úrovních.

**Determinismus zpracování.** Každá analytická úloha má přesně definovaný životní cyklus: `queued → running → completed / failed`. Přechody jsou řízeny atomickými Redis Lua skripty — nikdy nenastane situace, kde by úloha zmizela z fronty bez jasného výsledku. Opakované pokusy (retry) mají deterministický jitter vypočtený z ID úlohy a čísla pokusu — stejná úloha dostane vždy stejné zpoždění, což umožňuje předvídatelné testování a zabraňuje hromadnému opakování při kaskádovém selhání.

**Auditovatelnost.** Audit logy jsou ukládány jako strukturovaný JSONB (migrace 0039), což umožňuje dotazování na konkrétní akce bez parsování textu. Každá změna citlivého stavu (přihlášení, změna hesla, administrátorská akce) generuje záznam s kontextem. Verzování analytických a ceníkových profilů zajišťuje, že je vždy možné dohledat, jaká pravidla platila v okamžiku vzniku konkrétní nabídky.

**Kontrolované zpracování.** Backpressure subsystém (modul `app/core/backpressure.py`) aktivně řídí tok úloh: při přetížení fronty systém odmítne nové úlohy s HTTP 429 dříve, než dojde k přetečení paměti nebo degradaci výkonu. Kritické úlohy (přepočet nabídky) mají prioritní vstup do fronty před standardními úlohami.

**Jasné chování při chybě.** Pokud je Redis nedostupný, autentizační throttle nepadne na lokální in-memory fallback — vrátí HTTP 503. Pokud migrace databáze není aplikována, aplikace nenaběhne. Pokud worker ztratí lease na zpracovávanou úlohu, reaper ji po timeoutu přeřadí. Systém je nastaven tak, aby selhání bylo viditelné a kontrolované, ne tiché.

---

## 4. Hardening, bezpečnost a stabilita

### Autentizace a správa session

Přihlášení generuje pár krátkodobý access token / dlouhodobý refresh token. Od verze v0.7.000 jsou session sledovány v databázové tabulce `user_sessions` — uživatel vidí aktivní zařízení a může jednotlivé session vzdáleně ukončit (force logout). Sloupcový `token_version` na záznamu uživatele umožňuje deterministicky zneplatit všechny tokeny bez procházení celé tabulky revokací.

Per-account brute-force ochrana je implementována přes Redis jako sdílené úložiště — funguje korektně i při více instancích API. Při výpadku Redisu přechází do fail-closed módu (HTTP 503), nikoli do degradovaného stavu s lokálním čítačem.

### Multi-tenancy a izolace dat

Tenant izolace je strukturální vlastnost datového modelu, ne middleware vrstva. Každý ORM dotaz na uživatelská data filtruje přes `organization_id`. Pracovní katalog používá sparse delta model — tenant rows existují pouze tam, kde se tenant odchyluje od globálního výchozího nastavení, bez duplikace globálního katalogu pro každého tenanta.

Timing oracle obrana (`app/core/tenant_timing.py`) zajišťuje minimální dobu odpovědi na citlivých cestách — útočník nemůže z doby odpovědi odvodit, zda tenant ID existuje nebo ne.

### Worker a queue hardening

Každá analytická úloha ve zpracování je pojištěna leasem s vlastnickým tokenem (`lease_token + worker_id`). ACK při dokončení ověří, že lease stále patří danému workeru — pokud reaper lease přebral (timeout), ACK selže a nový worker úlohu zpracuje čistě. Lua skripty zajišťují, že enqueue, dequeue a ACK jsou atomické operace bez race condition.

Startup reconciliation (od v0.7.001) po restartu workeru porovná stav Redis fronty s databází a smaže orphaned záznamy — stav fronty a stav databáze jsou po startu vždy konzistentní.

### Omezení kaskádových selhání

Backpressure snapshot agreguje hloubku fronty, počet zpracovávaných úloh a retry inflight přes obě worker lanes (analýza + heavy export). Pokud globální kapacita překročí konfigurovaný strop, nové požadavky jsou odmítnuty s 429 — fronta se nepřeplní a Redis nezahltí paměť.

Worker a API jsou oddělené procesy s vlastními databázovými connection pooly — přetížení workeru neovlivní latenci API a naopak.

---

## 5. Rizika a jejich řízení

### Rizika existují — a jsou pojmenovaná

Projekt prošel třemi formálními audity bezpečnosti a provozní připravenosti (AUDIT_2026-03-31, AUDIT_PILOT_2026-04-02, AUDIT_PILOT_2026-04-02_v2). Každý audit klasifikuje rizika jako P0 (blokuje nasazení), P1 (blokuje škálování) a P2 (opravit v prvním sprintu). Výsledky auditů přímo generovaly kód v následujících releasech.

### Aktuální stav rizik (po v0.7.001)

**Rizika opravená nebo mitigovaná:**

- Fail-closed auth throttle (P0 z auditu → opraveno v v0.7.001)
- Worker healthcheck pro Docker orchestrátor (P0 → opraveno v v0.7.000)
- Backpressure subsystém zabraňující přetečení fronty (P1 → opraveno v v0.7.001)
- Per-session revokace tokenů (P0 → opraveno v v0.7.000)
- Deterministic retry jitter zabraňující thundering herdu (P1 → opraveno v v0.7.001)

**Rizika identifikovaná, čekající na opravu před go-live (P0):**

- Chybí `Content-Security-Policy` HTTP header — zvyšuje povrch pro XSS útok
- Chybí fallback větev ve worker finalize state machine — neznámý disposition stav by ponechal lease viset
- Ověření tenant filtru v `AnalysisService.get_job()` na DB úrovni — log existuje, DB filtr nutno explicitně potvrdit
- Hardcoded seed hesla v bootstrap souboru — nutno zajistit `DB_SEED_ON_STARTUP=false` v produkci
- Chybí produkční guard pro `METRICS_AUTH_ENABLED=false`

Tato rizika jsou dokumentovaná, rozsah jejich dopadu je pochopený a oprava každého z nich je odhadnuta na 1–3 hodiny práce. Go-live před jejich opravou není doporučen.

### Jak systém degraduje kontrolovaně

Při výpadku Redisu: API vrací 503 na auth endpointech (fail-closed); worker přestane přijímat nové úlohy (lease renewal selže); fronta se nevyprázdní, ale nezaplave paměť.

Při výpadku databáze: API vrací 503; worker dokončí aktuálně zpracovávanou úlohu (nebo selže při commitu), lease expiruje a reaper úlohu přeřadí po obnově spojení.

Při přetížení AI providera: úlohy se frontují s exponenciálním backoffem; kapacitní limit fronty zabraňuje hromadění tisíců čekajících úloh; nové požadavky dostávají 429 s jasnou chybovou zprávou.

---

## 6. Kompatibilita a robustnost

### Architektonická kompatibilita

Systém je kontejnerizovaný (Docker Compose) a bez zásahu do kódu přenositelný na jakýkoliv Linux host s Dockerem. Nginx je připraven na HTTPS terminaci s vlastními certifikáty. Storage backend je pluggable — pro vývoj a testování je k dispozici lokální souborový backend, pro produkci S3-compatible storage (AWS S3, MinIO, Cloudflare R2 nebo jakýkoliv S3-API kompatibilní provider).

Databázové schéma je verzováno přes Alembic s 40 migraci. Každá migrace je opatřena `down_revision` — rollback je možný. Startup blokuje spuštění, pokud není aktuální migrace aplikována.

AI provider je abstrahovaný za `StagedVisionPipeline` protokolem — přechod na jiného providera nevyžaduje změny v business logice, pouze implementaci nového adaptéru.

### Robustnost vůči provozním problémům

| Scénář                       | Chování systému                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------ |
| Redis restart (30 s výpadek) | Auth vrací 503; po obnově plná funkčnost automaticky                                                   |
| Worker crash                 | Reaper po lease timeoutu (výchozí 10 min) přeřadí úlohy; startup reconciliation smaže orphaned záznamy |
| DB connection spike          | Worker pool a API pool jsou oddělené; přetížení jednoho neovlivní druhý                                |
| Storage slowdown             | Analýzy čekají na fetch fotografie; worker lease je obnovován průběžně; timeout 30 min pro heavy joby  |
| Přetížení AI providera       | Retry s exponenciálním backoffem; kapacitní limit fronty; 429 pro nové požadavky                       |
| Neplatná migrace             | Startup odmítne nastartovat s explicitní chybou                                                        |

### Dlouhodobá udržitelnost

Katalog prací (43 typů, parametry, analytické a ceníkové profily) je navržen jako evolvovatelná struktura — přidání nového typu práce nebo úprava parametrů nevyžaduje změny kódu aplikace, pouze přidání záznamu do katalogu. Verzování profilů zajišťuje, že změna katalogu neovlivní historické nabídky.

Testy pokrývají kritické cesty: worker queue atomicitu, lease ownership, backpressure kapacitu, retry backoff, tenant izolaci, auth flow. Kontinuální rozšiřování testovací základny je součástí každého releasu.

---

## 7. Pilotní nasazení

### Co znamená pilot

Pilotní nasazení je kontrolovaný přechod systému z vývojového prostředí do reálného provozu s omezeným počtem tenantů a uživatelů. Není to zkrácená verze produkčního provozu — je to explicitní fáze, ve které se ověřují předpoklady, které v testovacím prostředí nelze plně simulovat.

### Cíle pilotu

1. **Ověřit stabilitu pod reálnou zátěží** — reálné fotografie (ne testovací data), reálné uživatelské chování, reálné časové vzory přístupu
2. **Ověřit AI pipeline na produkčních datech** — testovací data mají jiné charakteristiky než terénní fotodokumentace; pilot odhalí případné slepé skvrny detekce nebo mapování
3. **Ověřit provozní observabilitu** — fungují alerting, metriky a logy tak, aby bylo možné identifikovat problém dřív než ho uvidí uživatel
4. **Ověřit onboarding tenanta** — vytvoření tenanta, první projekt, první analýza, první nabídka — bez asistence vývojáře
5. **Získat reálná kapacitní data** — viz část 8

### Co se v pilotu ověřuje

- Průchodnost celého flow od uploadu fotografie po exportovanou nabídku bez ručního zásahu do systémových vrstev
- Chování systému při chybě AI providera (timeout, chybná odpověď, nerozpoznatelný vstup)
- Čas zpracování analýzy pod reálnými podmínkami
- Konzistence dat po restartu workeru nebo API
- Správnost tenant izolace s více simultánně aktivními tenanty

### Pilot jako kontrolovaný přechod

Pilot běží na produkční infrastruktuře (ne na vývojovém stroji), ale s omezeným počtem tenantů a monitorovaným prostředím. Před pilotem jsou aplikovány všechna P0 rizika z posledního auditu. Výstupem pilotu nejsou jen funkční výsledky — jsou to konkrétní metriky: průměrný čas analýzy, počet selhání, počet retry úloh, využití fronty, chybovost storage. Tato data definují základnu pro kapacitní plánování.

---

## 8. Kapacitní a provozní otázky

### Kolik tenantů a analýz lze souběžně zpracovávat

Přesná čísla nelze uvést bez naměřených dat z pilotu. Níže jsou architektonické parametry, na kterých kapacita závisí.

**Tenant kapacita** závisí na:

- Počtu worker procesů (konfigurováno přes `WORKER_CONCURRENCY`)
- Hloubce fronty (`ANALYSIS_QUEUE_MAX_DEPTH`, výchozí 1 000 úloh)
- Per-tenant limitu simultánních analýz (konfigurovatelný, výchozí není veřejně specifikován — ověřit před pilotem)
- Výkonu AI providera (latence Claude API nebo jiného providera)

**Analytická kapacita** závisí na:

- Době zpracování jedné analýzy (dominuje čas AI volání — typicky 10–180 s v závislosti na provideru a složitosti)
- Počtu worker slotů
- Kapacitě DB connection poolu pro worker

**Ilustrativní příklad (ne garance):** Při 4 worker slotech a průměrné době analýzy 60 s je teoretická propustnost ~240 analýz/hodinu. Skutečné číslo bude nižší kvůli overhead (DB operace, storage, lease management) a vyšší při kratší latenci AI providera. Tato čísla je nutné ověřit měřením.

### Za jakých podmínek systém běží bez chyb

Systém je navržen tak, aby při překročení kapacity odmítl nové požadavky (HTTP 429), nikoli aby degradoval bez varování. Podmínky pro stabilní provoz:

- Redis dostupný a s dostatečnou pamětí pro frontu a cache
- Databáze s výkonem adekvátním počtu simultánních connections (API pool + Worker pool)
- S3 storage dostupná a s dostatečnou propustností pro upload a fetch fotografií
- AI provider dostupný — výpadek providera způsobí nárůst retry, nikoli ztrátu dat

### Jak se kapacita ověřuje

Projekt obsahuje `scripts/run-pilot-load-rehearsal.py` a `scripts/run-operational-load-rehearsal.py` — spustitelné skripty pro zátěžové simulace s mock AI providerem. Simulace ověřují auth flow, upload fotografií, frontu analýz a worker drain bez závislosti na externím AI API. Výsledky simulace jsou základem pro kapacitní odhad před ostrým pilotem.

---

## 9. Simulace a ověřování

### Proč jsou simulace nutné

Stability a performance claims bez měření jsou pouze předpoklady. Projekt to reflektuje: každý nový subsystém je doprovázen integračními testy, každý provozní drill má spustitelný skript, každý release je verzován a zdokumentován.

### Co je pokryto simulacemi a testy

- **Worker queue atomicita** — testy ověřují, že Lua skripty správně hlídají kapacitu, ownership leasu a atomicitu ACK/DLQ přechodů
- **Retry backoff** — deterministický jitter je testován pro různá kombinace job ID a čísla pokusu
- **Account throttle** — testy ověřují fail-closed chování při výpadku Redisu
- **Backpressure** — testy ověřují, že priority routing a kapacitní limity fungují pod kombinovanou zátěží obou worker lanes
- **Tenant izolace** — testy ověřují, že dotazy přes tenant boundary vrátí 404, nikoli data jiného tenanta
- **Worker startup reconciliation** — testy ověřují čistění orphaned záznamu po restartu
- **Operační resilience drill** — scénáře zahrnující restart Redisu, crash workeru, spike DB connections a storage zpomalení

Detailní incident rehearsal scénáře pro pilot a go-live validaci jsou sepsané v [docs/incident-rehearsal-scenare.md](./incident-rehearsal-scenare.md).

### Kde jsou limity testů

Integrační testy běží s mock AI providerem — nepokrývají latenci a chybovost reálného AI API. Zátěžové testy s mock providerem dávají kapacitní odhad pro "ideální" podmínky. Reálná kapacita s Claude API nebo jiným externím providerem bude nutně nižší. Tento rozdíl je nutné změřit v pilotu.

---

## 10. Škálování pro 100k+ využití

### Výhled a podmínky růstu

Architektura NOVU Builderu byla navržena s vědomím budoucího škálování, ale aktuální verze je dimenzována pro pilotní a raný produkční provoz. Níže jsou podmínky, které musí být splněny pro škálování k 100k+ využití (100k analýz/měsíc nebo 100k+ aktivních tenantů).

### Architektonické předpoklady pro škálování

**Horizontální škálování API:** FastAPI backend je stateless (session state je v Redisu a DB) — přidání dalších API instancí za load balancer je přímočaré. Vyžaduje: Redis cluster nebo Redis Sentinel pro HA, připojení všech instancí ke sdílenému Redis (account throttle je fail-closed, ne per-instance).

**Horizontální škálování workerů:** Worker process je navržen jako stateless runner — přidání dalších worker instancí zvyšuje propustnost fronty lineárně. Vyžaduje: koordinaci `BACKPRESSURE_MAX_CONCURRENT_JOBS` s celkovým počtem slotů, monitoring lease reaperu na každé instanci.

**Databáze:** Aktuální architektura předpokládá jednu primární PostgreSQL instanci. Pro 100k+ využití je nutné zvážit: read replicas pro čtecí dotazy (katalog, projekty), connection pooling přes PgBouncer, případně sharding tenantů na více instancí. Toto je zásadní architektonická práce, která je v aktuální verzi nepřítomna.

**Redis:** Pro velký počet tenantů s aktivním cacheováním katalogů a session dat poroste paměťová náročnost Redisu. Nutno monitorovat a případně přejít na Redis Cluster.

**AI provider kapacita:** Škálování analytické propustnosti je přímo závislé na kapacitě AI API (rate limits, concurrent requests). Při 100k analýzách/měsíc (~140/hodinu průměr, ale zátěž je nerovnoměrná) je nutné mít sjednané dedikované limity s providerem nebo distribuovat zátěž přes více API klíčů.

### Provozní disciplína pro škálování

Škálování nestojí jen na infrastruktuře. Podmínky na provozní úrovni:

- **Observabilita:** Prometheus metriky jsou implementovány; pro 100k+ využití je nutné mít dashboardy s alertingem na backpressure, worker queue hloubku, error rate a latenci AI API
- **Sentry traces:** Aktuálně na 0 % sampling — pro škálování nutno zapnout (doporučeno 5 % pro pilot, 1–2 % pro produkci)
- **Kapacitní testy před každou fází růstu:** Nelze škálovat bez změřené základny; každý 10× nárůst počtu tenantů nebo analýz vyžaduje ověření simulací
- **Migrační disciplína:** 40 migrací proběhlo bez incidentu; pro 100k+ je nutné mít rollback plán pro každou migraci a testovat ji na produkční kopii dat

### Co není v současné verzi a je nutné pro 100k+

| Oblast                  | Aktuální stav                          | Co je potřeba                |
| ----------------------- | -------------------------------------- | ---------------------------- |
| DB HA                   | Jednoduchá instance                    | Read replicas, PgBouncer     |
| Redis HA                | Standalone                             | Redis Sentinel nebo Cluster  |
| Worker koordinace       | Jednoduchý runner                      | Distribuovaná správa workerů |
| AI provider rate limits | Bez dedikované smlouvy                 | Sjednané API limity          |
| Monitoring              | Metriky implementovány, traces vypnuty | Plný observability stack     |

Tyto body nejsou nedostatky současné verze — jsou to předvídatelné kroky při řízené cestě od pilotu k plné produkci.

---

## Executive Summary

NOVU Builder je backendový systém pro automatizaci stavebních cenových nabídek na bázi AI analýzy fotografií a katalogem řízené kalkulace. Systém propojuje mobilní sběr terénních dat, strukturovanou AI pipeline (detekce → extrakce → mapování na katalog 43 prací) a řízené zpracování pro kancelářský výstup.

Architektura je navržena pro multi-tenant SaaS provoz s důrazem na deterministické zpracování, auditovatelnost a kontrolované chování při selhání. Klíčové principy: fail-closed bezpečnost (žádné tiché degradace), atomické queue operace přes Redis Lua skripty, lease-based worker model s garbage collection, a backpressure subsystém zabraňující přetěžování systému.

Projekt je ve verzi v0.7.001 s 40 databázovými migracemi, třemi formálními bezpečnostními audity a sadou provozních rehearsal skriptů. Před pilotním nasazením zbývá uzavřít 5 identifikovaných P0 rizik (odhad ~6 hodin práce). Kapacitní čísla pro produkční provoz jsou závislá na měření v pilotu — projekt pro tento účel obsahuje zátěžové testovací nástroje.

---

## Investiční / partnerská verze

NOVU Builder řeší konkrétní a opakovaný problém ve stavebnictví: generování cenových nabídek je dnes ruční, pomalé a závislé na jednotlivci. Systém automatizuje tento tok od terénní fotodokumentace po strukturovaný návrh nabídky s katalogem 43 prací a AI pipeline. Jde o multi-tenant SaaS s architekturou navrženou pro řízený provoz, nikoliv o demo. Tři formální audity za poslední týden ukázaly, že tým aktivně identifikuje a řeší provozní rizika místo jejich ignorování. Před pilotem zbývá uzavřít dokumentovaná P0 rizika — všechna jsou identifikována, rozsah i oprava jsou jasné. Kapacitní odhady pro produkci budou ověřeny pilotem s měřením, ne přijaty jako axiom. Škálování k 100k+ využití vyžaduje databázovou HA, Redis cluster a sjednané AI API limity — tyto kroky jsou identifikované a nepředstavují architektonické překvápení. Systém je připraven na pilotní nasazení s prvními reálnými tenanty jako základ pro validaci obchodní hodnoty i technické kapacity.

---

## Tvrzení vyžadující ověření pilotem nebo měřením

Následující body jsou architektonické předpoklady nebo odhadnuté hodnoty, které nesmí být prezentovány jako fakta bez naměřených dat:

1. **Průměrná doba analýzy** — závisí na AI providerovi, složitosti fotografií a počtu workerů; nutno změřit v pilotu
2. **Propustnost analýz/hodinu** — teoretický výpočet ze slotů a latence; reálné číslo bude nižší kvůli overhead
3. **Per-tenant limit simultánních analýz** — konfigurovatelný parametr; výchozí hodnotu a chování při překročení ověřit v kódu a zdokumentovat
4. **Kapacita tenant base bez degradace výkonu** — závisí na DB, Redis a storage výkonu; nutno změřit zátěžovým testem
5. **Přesnost AI detekce na reálných datech** — testovací data nereprezentují plně terénní podmínky; nutno ověřit na vzorku pilotních zakázek
6. **Chybovost AI pipeline** — počet analýz s validačními varováními nebo nerozpoznaným typem práce je dosud neznámý na reálných datech
7. **Čas onboardingu nového tenanta** — od registrace po první odeslanou nabídku; nutno projít s reálným uživatelem
8. **Stabilita worker procesu při 24/7 provozu** — krátkodobé testy nezachytí paměťové úniky nebo postupnou degradaci; nutno ověřit v pilotu minimálně 7 dnů
9. **Redis paměťová náročnost při 50+ aktivních tenantech** — závisí na cache TTL a intenzitě přístupu; nutno profilovat
10. **DB query latence při 10k+ projektech v jednom tenantovi** — indexy jsou přítomny, ale mezní výkon není změřen

---

_Dokument vychází výhradně z analýzy kódu, databázových migrací a auditních zpráv projektu NOVU Builder v0.7.001. Nepracuje s externími zdroji ani předpoklady mimo kódovou základnu._

_Připraveno: 2. dubna 2026_
