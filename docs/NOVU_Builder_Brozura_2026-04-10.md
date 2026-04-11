# NOVU Builder

## Projektová brožura pro B2B, investiční a enterprise partnery

Stav dokumentu: 10. dubna 2026  
Hodnocený stav: řízený pilot / near-production, nikoli full enterprise production

---

## 1. Title Page

**NOVU Builder**  
Řízený systém pro zpracování zakázek, analýzu fotografií a přípravu cenových podkladů.  
Navrženo pro kontrolovaný provoz, auditovatelné workflow a postupné škálování bez ztráty provozní disciplíny.

---

## 2. Executive Summary

NOVU Builder je vícevrstvý systém pro sběr terénních dat, serverové zpracování zakázek, AI-assisted analýzu obrazových vstupů a přípravu obchodně použitelných výstupů. Prakticky řeší tok od založení případu a nahrání fotodokumentace přes asynchronní analýzu a workflow kontrolu až po návrh a export finálních podkladů.

Systém je určen pro firmy, které potřebují opakovatelně a pod kontrolou zpracovávat technické nebo obchodní případy nad fotodokumentací. Typický uživatel je provozní tým, kalkulant, office manager, partner s více pobočkami nebo enterprise zákazník s požadavkem na tenant isolation, auditovatelnost a předvídatelné chování systému.

Aktuální stav je vhodné popsat jako **controlled pilot / near-production**. Backend, queue orchestrace, auth, auditní vrstva a provozní guardraily jsou funkční. Současně je transparentní, že plná enterprise připravenost ještě vyžaduje dotažení load safety, monitoring kontraktu, Redis failure isolation a úplného disaster recovery kontraktu.

Hlavní síla systému je v tom, že je od začátku navržen jako robustní a deterministický. Kritické části se nespoléhají na tiché fallbacky, systém rozlišuje autoritativní datovou pravdu od runtime transportu a v chybových stavech preferuje řízené odmítnutí nebo degradaci před neviditelnou nekonzistencí.

---

## 3. Problém, Který Řešíme

Ve firmách se dnes velká část práce nad fotografickou dokumentací a následným obchodním zpracováním stále děje ručně. Data přicházejí nesjednoceně, workflow bývá rozpadlé mezi e-mail, chat, tabulky a ad hoc rozhodování, a výsledek je závislý na zkušenosti jednotlivce, ne na systémové opakovatelnosti.

Nejčastější slabiny současného stavu:

- neexistuje jednotný vstup pro fotografie, metadata a stav případu
- AI nebo automatizace bývá připojena bokem, bez auditní stopy a bez jasné odpovědnosti za finální rozhodnutí
- výpočet, validace a export se často míchají do jednoho křehkého workflow
- při chybě není jasné, co je autoritativní stav a co je pouze dočasný runtime signál

Dopady jsou konkrétní: ztráta času, vyšší chybovost, slabá dohledatelnost změn, těžké onboardování nových týmů a vysoké provozní riziko při růstu počtu klientů nebo tenantů.

---

## 4. Řešení: NOVU Builder

NOVU Builder odděluje vstup, rozhodování a zpracování do jasných vrstev. Mobilní klient sbírá vstup, desktop klient slouží jako kontrolní a pracovní vrstva, backend je zdroj pravdy a AI vrstva dodává strukturovaný návrh, nikoli finální obchodní rozhodnutí.

High-level flow:

1. Uživatel založí případ a nahraje fotodokumentaci.
2. Backend validuje vstup, uloží metadata a zapíše autoritativní stav do databáze.
3. Analýza se zařadí do fronty a převezme ji worker s lease-based zpracováním.
4. AI / analysis layer vrátí strukturovaný výstup nad definovaným kontraktem.
5. Backend výsledek zapíše, zpřístupní office workflow a připraví export nebo další zpracování.

Klíčové komponenty:

- **Backend:** FastAPI, multi-tenant datový model, REST API, auth, workflow, audit, storage politika a fail-fast validace konfigurace.
- **Worker processing pipeline:** Redis-backed queue, lease ownership, retry budget, dead-letter handling, backpressure a oddělení processing plane od API plane.
- **AI / analysis layer:** provider abstraction, staged pipeline, mock i reálné providery, AI jako návrhová vrstva pod kontrolou serverových pravidel.
- **Storage a data model:** PostgreSQL jako autoritativní relační vrstva, S3-compatible storage jako autoritativní byte storage v produkčním režimu, DB ukládá storage keys místo veřejných URL.

---

## 5. Aktuální Stav Systému

### Co je hotové

- kanonický backend s více než 40 verzovanými migracemi a oddělením route / service / repository vrstev
- multi-tenant auth a session model včetně revokace tokenů, session invalidace a auditních záznamů
- health, readiness a processing readiness kontrakty pro API a background processing
- worker orchestrace pro analysis jobs včetně retry, stale lease recovery a DLQ toku
- storage vrstva pro uploady, exporty a signed URL model
- provozní skripty pro backup, restore, smoke verifikaci a load rehearsals
- funkční Qt6 desktop prototyp napojený na reálné backend API pro hlavní office workflow

### Co je ověřeno

- tenant isolation, auth guardraily, rate limiting a část security hardeningu jsou pokryté cílenými testy a opakovanými audity
- queue/backpressure/retry model má dokumentované a zčásti automatizovaně ověřené failure scénáře
- backup/restore cesta pro DB je deterministická a fail-closed
- lokální guardrail verifikace dne 10. dubna 2026 prošla v rozsahu 157/159 vybraných testů; zbývající dvě chyby jsou soustředěné v DLQ reprocess flow

### Co ještě není finální

- load-safe runtime profil není ještě plně uzavřený pro vyšší paralelní provoz
- monitoring vrstva existuje, ale část alertů a probe kontraktů ještě vyžaduje zpřesnění
- Redis failure isolation ještě není dostatečně oddělena mezi auth, queue a cache rolemi
- full-state disaster recovery je navržen správným směrem, ale stále potřebuje sjednocenou provozní pravdu a tvrdší off-site kontrakt

---

## 6. Bezpečnost a Stabilita

Bezpečnostní model stojí na principech, které jsou vhodné i pro náročnější B2B prostředí:

- **fail-closed design:** při nedostupnosti kritické ochranné vrstvy systém raději vrátí chybu nebo znepřístupní část provozu, než aby ochranu obešel
- **tenant isolation:** organizační hranice nejsou jen UI konvence; jsou součástí datového modelu, dotazů i testů
- **audit trail:** citlivé operace se zapisují do auditní vrstvy jako samostatná autoritativní pravda

Provozní stabilita je postavena na oddělení API readiness a processing readiness, na lease-based worker modelu, bounded retries a backpressure. Systém už dnes umí signalizovat, kdy je API dostupné, ale background processing není bezpečně připravený. To je důležitý rozdíl oproti běžnému SaaS, kde bývá zelený health endpoint i při skryté degradaci fronty nebo workerů.

Odlišující vlastnost není „více funkcí“, ale tvrdší provozní kontrakt: databáze je autoritativní pro business stav, Redis je runtime transport, storage politika je explicitní a failure mode jsou navržené tak, aby byly viditelné.

---

## 7. Provozní Připravenost

Systém už exportuje širokou sadu metrik pro HTTP vrstvu, databázi, worker heartbeat, queue depth, retry tlak, storage operace, auth ochranu a auditní selhání. Existuje alerting baseline a provozní runbooky pro restart, outage a recovery scénáře.

Incident preparedness je založena na definovaných rehearsal scénářích: Redis restart, worker crash během jobu, external API failure storm, retry storm a queue saturation. Očekávané chování je popsáno předem, včetně toho, které signály musí systém ukázat a jak má vypadat recovery bez ručních DB zásahů.

Determinismus systému je důležitá architektonická vlastnost. Job lifecycle má explicitní stavy, retry má omezený budget, queue growth je bounded a backpressure je first-class mechanismus. To omezuje „náhodné“ provozní stavy a zvyšuje reprodukovatelnost incidentů i testů.

---

## 8. Škálování a Cílový Stav

### Pilot

Reálně vhodný profil pro nejbližší fázi je **5–10 tenantů** s řízeným onboardingem, aktivním monitoringem a omezenou paralelní zátěží. Tato fáze má potvrdit provozní pravdu na reálných datech, ne jen architektonický záměr.

### Rozšíření

Profil **50–100 tenantů** je dosažitelný evolučně, nikoli redesignem, ale vyžaduje dotažení konkrétních opatření: zapnutou a oddělenou heavy lane, vyšší worker concurrency, přísnější tenant fairness mimo analysis lane, tvrdší observability kontrakt a lepší Redis/infra isolation.

### Cílový stav

Cíl **100k+ tenantů nebo velmi vysokého paralelního provozu** není marketingový claim pro dnešní verzi. Architektura k němu směřuje přes stateless API vrstvu, queue model, worker isolation a explicitní resource controls, ale plná cesta vyžaduje další kroky:

- Redis Sentinel nebo Cluster místo jednoho sdíleného failure domain
- databázovou HA vrstvu, connection pooling a pravděpodobně read replicas
- tvrdší oddělení auth, cache a queue runtime rolí
- infrastrukturní least-privilege a menší blast radius mezi službami
- smluvně zajištěnou kapacitu AI providerů

Směr škálování je tedy realistický, ale musí být ověřován po etapách a proti měřeným provozním datům.

---

## 9. Výkon a Limitace

Dnešní systém zvládá bezpečněji to, co mnoho pilotních systémů nezvládá vůbec: bounded queue growth, retry budget, worker recovery, signed storage access, auditní stopu a explicitní readiness chování.

Současné limity jsou známé a pojmenované:

- runtime load profil ještě není dostatečně tvrdý pro vyšší souběžný provoz bez dalšího ladění
- některé heavy operace ještě potřebují důslednější oddělení od request cesty
- část monitoringu a alert matematiky potřebuje srovnat s reálnou probe semantikou
- disaster recovery kontrakt ještě není uzavřený jako jediná provozní pravda

Důležité je, že tyto limity neimplikují nutnost architektonického restartu. Jde o evoluční hardening: zvýšení concurrency, oddělení failure domains, dotažení observability, tvrdší infra profil a pravidelné rehearsal ověřování.

---

## 10. Roadmapa

**Stabilizační fáze**  
Uzavření DLQ/reprocess detailů, monitoring kontraktu, Redis role separation, hardening entrypointu a přesnější load-safe runtime profil.

**Pilot rollout**  
Nasazení do kontrolovaného provozu, měření queue drain, latencí, retry tlaku, storage chyb a tenant onboarding toku na reálných datech.

**Škálování**  
Postupné navýšení concurrency, oddělení heavy lane, tenant fairness mimo analysis lane, lepší infra segmentace a HA prvků.

**Enterprise readiness**  
Jednoznačný DR kontrakt, off-site recovery discipline, přísnější secrets a identity model, menší blast radius a dashboard / alerting vrstva bez semantického driftu.

---

## 11. Proč NOVU Builder

NOVU Builder není postaven jako demo s nadějí, že se později „nějak zprodukční“. Je stavěn opačně: nejprve provozní disciplína, potom rozšiřování možností.

- stabilita má přednost před šířkou funkcí
- bezpečnost má přednost před rychlostí vývoje
- kontrola systému má přednost před improvizovaným růstem

Právě proto je vhodný pro reálné nasazení v kontrolovaném pilotu a pro partnery, kteří potřebují vidět nejen funkčnost, ale i schopnost systému zvládat chybu, růst a audit.

---

## 12. Závěr

NOVU Builder je dnes technicky důvěryhodný základ pro řízený pilot a následné hardeningové rozšíření do enterprise provozu. Není korektní jej prezentovat jako plně uzavřený hyperscale produkt. Je korektní jej prezentovat jako systém, který má správně navržené provozní jádro, transparentně pojmenované limity a realistickou cestu ke škálování bez chaosu.

**System is built for controlled, reliable scaling — not experimental deployment.**
