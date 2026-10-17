# NOVU Builder – auditní brožura pro PDF

Datum dokumentu: 29. dubna 2026  
Jazyk: čeština  
Formát: A4 portrait, vícestránková technická brožura pro investory, zákazníky a produktovou prezentaci

## A) PAGE STRUCTURE

Strana 1 – Titulní strana  
Strana 2 – Executive Summary  
Strana 3–4 – Původní vs aktuální směr  
Strana 5–7 – Produkt: co dělá  
Strana 8–10 – Silné stránky  
Strana 11–13 – Srovnání s trhem  
Strana 14–15 – Odlišení  
Strana 16–17 – Budoucí rozvoj  
Strana 18–19 – Rizika  
Strana 20 – Bezpečnost + stabilita  
Strana 21 – Škálování  
Strana 22 – Závěr

## B) GLOBAL DESIGN SYSTEM

Formát: A4 na výšku, 210 × 297 mm.  
Okraje: 20 mm ze všech stran.  
Grid: 12 sloupců, gutter 4 mm, aktivní textová šířka 170 mm.  
Primární barva: #0B1F3A.  
Sekundární akcent: #2E6BFF.  
Neutrální pozadí: #F5F7FA.  
Text: #111111.  
Rizika a upozornění: #E63946.  
Nadpisy: Montserrat Bold.  
Podnadpisy: Montserrat SemiBold.  
Text: Times New Roman Regular.  
H1: 30 pt, řádkování 34 pt.  
H2: 20 pt, řádkování 24 pt.  
H3: 15 pt, řádkování 19 pt.  
Body text: 11.5 pt, řádkování 15 pt.  
Popisky tabulek a mikrotext: 9 pt, řádkování 12 pt.  
Zvýraznění: tučné, barva #2E6BFF.  
Linky: 0.5–1 pt, #D7DDE8 nebo #2E6BFF podle významu.  
Styl: technický, čistý, s vysokým kontrastem; žádné dekorativní ilustrace, žádné gradientové hero efekty.

Komponenta HIGHLIGHT BOX: pozadí #F5F7FA, levý pruh 4 mm v #2E6BFF, vnitřní padding 6 mm, nadpis Montserrat SemiBold 12 pt, text Times New Roman 11 pt.  
Komponenta RISK BOX: pozadí #FFF4F5, levý pruh 4 mm v #E63946, nadpis #E63946, stejný padding jako highlight box.  
Komponenta COMPARISON TABLE: záhlaví #0B1F3A s bílým textem, tělo bílé, střídavé řádky #F5F7FA, linky #D7DDE8, text 9.5–10 pt.

## C) CONTENT + DESIGN INSTRUCTIONS PER PAGE

=== PAGE 1 ===

[LAYOUT]

12sloupcový grid. Horní meta blok přes 4 sloupce vpravo. Hlavní titul přes 8 sloupců vlevo, umístění od 72 mm shora. Spodní informační blok přes celou šířku, výška 34 mm. Bez tabulek. Obsahuje text blok a highlight box.

[DESIGN]

Pozadí bílé. V horní části tenká horizontální linka #2E6BFF přes 12 sloupců. Vlevo vertikální pruh #0B1F3A šířky 8 mm od horního po spodní okraj tiskového pole. H1 Montserrat Bold 32 pt, barva #0B1F3A. Podtitul 15 pt Montserrat SemiBold, barva #111111. Spodní highlight box s levým akcentem #2E6BFF.

[CONTENT]

NOVU Builder  
Auditní brožura produktu, architektury a škálovatelnosti

Technický audit a business interpretace systému pro sběr fotodokumentace, AI asistovanou analýzu, řízení zakázky a přípravu cenových podkladů.

Stav dokumentu: 29. dubna 2026  
Určeno pro: investory, zákazníky, produktovou prezentaci  
Hodnocený stav: řízený pilot / near-production foundation

HIGHLIGHT BOX  
NOVU Builder není obecný chatbot ani klasická inspekční aplikace. Jádrem produktu je řízený tok zakázky: terénní vstup, serverová validace, AI návrh, lidská kontrola, katalog prací, cenový výstup a auditovatelná historie změn.

---

=== PAGE 2 ===

[LAYOUT]

12 sloupců. H2 přes 12 sloupců nahoře. Levý textový blok přes 7 sloupců. Pravý sloupec přes 5 sloupců se dvěma highlight boxy. Spodní třetina: třísloupcový souhrn „Produkt / Architektura / Stav“. Bez obrázků.

[DESIGN]

Nadpis #0B1F3A. Pravé highlight boxy na pozadí #F5F7FA s modrým pruhem. Spodní souhrn jako tři bílé bloky s horní linkou #2E6BFF. Klíčové pojmy tučně a modře.

[CONTENT]

Executive Summary

NOVU Builder je systém pro firmy, které potřebují rychle a opakovatelně převést terénní fotodokumentaci do kontrolovaného pracovního toku a následně do technicky obhajitelného cenového podkladu. Produkt propojuje mobilní sběr vstupů, kancelářské ověření v desktopovém prostředí, backend jako zdroj pravdy, AI analýzu fotografií a katalog prací řízený stabilním `workTypeCode`.

Aktuální hodnota projektu není v jedné samostatné funkci, ale v architektonickém směru: systém odděluje návrh od rozhodnutí. AI může navrhnout plochu, typ poškození, materiály nebo pracovní postup, ale finální stav zakázky, výpočet a schválení zůstává na serveru a pod kontrolou uživatele.

HIGHLIGHT BOX  
Nejdůležitější investiční teze: NOVU Builder vytváří auditovatelnou doménovou vrstvu mezi obecnou AI a konkrétním stavebním obchodním procesem. Tato vrstva je hůře kopírovatelná než samotné volání AI modelu.

HIGHLIGHT BOX  
Nejdůležitější zákaznická teze: systém má zkrátit čas od fotky k nabídce, ale bez toho, aby firma ztratila kontrolu nad cenou, odpovědností a historií rozhodnutí.

Produkt: photo-to-workflow-to-offer systém pro stavební a servisní zakázky.  
Architektura: Qt desktop + FastAPI backend + PostgreSQL + Redis + S3 + AI worker.  
Stav: vhodné pro řízený pilot; enterprise provoz vyžaduje další hardening monitoringu, DR, load profilu a Redis izolace.

---

=== PAGE 3 ===

[LAYOUT]

12 sloupců. Dvoustranné srovnání 50/50: vlevo „Původní směr“, vpravo „Aktuální směr“. Každý panel má nadpis, 5 bodů a krátký závěr. Dole highlight box přes 12 sloupců.

[DESIGN]

Levý panel neutrální #F5F7FA, pravý panel bílý s horní linkou #2E6BFF. Nadpisy Montserrat SemiBold 18 pt. Šipka mezi panely jako textový symbol „→“ v #2E6BFF, 22 pt. Žádné dekorace mimo linky.

[CONTENT]

Původní vs aktuální směr: změna produktu

Původní směr  
Projekt začínal jako prototyp rychlé tvorby nabídek z fotek. Hlavní otázka byla: „Umíme z fotodokumentace dostat odhad rozsahu a nabídku?“ Tento směr měl hodnotu pro ověření workflow, datového modelu, cenové logiky a prvního kancelářského UX.

Charakter původního směru:
- důraz na rychlé ověření nápadu,
- prototyp kancelářské části,
- jednodušší runtime,
- menší důraz na provozní invarianty,
- AI pipeline primárně jako koncept.

Aktuální směr  
Aktuální směr je platformní. NOVU Builder se přesouvá ke kontrolovanému systému zakázky, kde je backend autoritou pro data, workflow, výpočty, audit a integrace. AI je specializovaná návrhová vrstva, ne rozhodovací centrum.

Charakter aktuálního směru:
- mobilní aplikace sbírá data v terénu,
- Qt desktop slouží jako kontrolní pracoviště,
- FastAPI backend rozhoduje, validuje a ukládá,
- PostgreSQL drží autoritativní stav,
- Redis a worker řeší asynchronní zpracování.

HIGHLIGHT BOX  
Změna směru není odklon od původní hodnoty. Je to přesun od prototypu nabídky k produktu, který může nést odpovědnost za reálný obchodní a provozní proces.

---

=== PAGE 4 ===

[LAYOUT]

12 sloupců. Horní text přes 8 sloupců, pravý callout přes 4 sloupce. Střed: procesní osa přes 12 sloupců se 6 kroky. Spodní část: krátká tabulka „Co se mění / Dopad“.

[DESIGN]

Procesní osa: tenká horizontální linka #2E6BFF, kroky jako očíslované body v #0B1F3A. Tabulka se záhlavím #0B1F3A. Callout jako highlight box.

[CONTENT]

Původní vs aktuální směr: technický dopad

Nový směr mění odpovědnosti mezi vrstvami. Klienti nemají nést business logiku. Desktop může zobrazit návrh, umožnit korekci a poslat změnu. Server musí změnu ověřit, uložit, přepočítat a vytvořit auditní stopu. AI worker má vracet strukturovaný výstup, nikoli finální obchodní rozhodnutí.

HIGHLIGHT BOX  
Pravidlo architektury: mobil sbírá, desktop kontroluje, server rozhoduje a ukládá, AI navrhuje.

Procesní osa:
1. Terénní vstup: fotky, metadata, popis.  
2. Backend validace: tenant, velikost souborů, workflow stav.  
3. Storage: produkčně S3-compatible storage, v DB jen storage keys.  
4. AI job: fronta, lease, retry, provider, strukturovaný výsledek.  
5. Katalog prací: mapování přes `workTypeCode`.  
6. Kontrola a výstup: korekce, final proposal, PDF/DOCX export.

COMPARISON TABLE

| Kategorie | Původní prototyp | Aktuální směr |
|---|---|---|
| Primární otázka | Umí systém vytvořit nabídku z fotek? | Umí systém řídit auditovatelný tok zakázky? |
| Role AI | Generátor odhadu | Návrhová vrstva pod serverovou kontrolou |
| Klientská vrstva | Kancelářský prototyp | Qt desktop pro kontrolu, mobil pro sběr |
| Zdroj pravdy | Smíšený prototypový model | PostgreSQL + serverové workflow |
| Riziko růstu | Křehký runtime | Evoluční škálování přes fronty a guardraily |

---

=== PAGE 5 ===

[LAYOUT]

12 sloupců. H2 nahoře. Levý blok přes 6 sloupců „Co produkt řeší“. Pravý blok přes 6 sloupců „Pro koho“. Dole full-width workflow tabulka o 5 řádcích.

[DESIGN]

Vlevo bílé pozadí, vpravo highlight box. Workflow tabulka s tmavým záhlavím. Akcentované termíny #2E6BFF.

[CONTENT]

Produkt: co NOVU Builder dělá

NOVU Builder řeší praktický problém: technik nebo pracovník v terénu pořídí fotky a základní informace, ale firma potřebuje z těchto vstupů vytvořit kontrolovatelný, konzistentní a obchodně použitelný výstup. Bez systému vzniká mezera mezi fotkou, odhadem, cenou, odpovědností a finálním dokumentem.

Produkt převádí rozpadlý proces do řízeného toku:
- založení zakázky,
- nahrání fotek,
- serverová evidence a validace,
- AI asistovaná analýza,
- mapování na katalog práce,
- lidská kontrola a korekce,
- návrh cenových variant a export.

HIGHLIGHT BOX  
Typický uživatel není člověk, který si chce s AI popovídat. Je to kalkulant, manažer, servisní tým nebo stavební firma, která potřebuje opakovatelný postup a dohledatelný výsledek.

COMPARISON TABLE

| Krok | Vstup | Výstup |
|---|---|---|
| Sběr | Fotky, popis, metadata | Zakázka s uloženou dokumentací |
| Validace | Soubor, tenant, workflow stav | Přijatý nebo odmítnutý vstup |
| Analýza | Fotky a kontext projektu | Objekt, stav povrchu, rozsah, plocha, confidence |
| Katalog | AI návrh + konfigurace | `workTypeCode`, parametry, profily |
| Kontrola | Návrh systému | Upravený a schválený podklad |

---

=== PAGE 6 ===

[LAYOUT]

12 sloupců. Středová architektonická mapa přes celou šířku. Pět horizontálních vrstev: Mobil, Desktop Qt, Backend API, Worker/AI, Data/Storage. Pravý okraj obsahuje krátké poznámky k odpovědnosti vrstev.

[DESIGN]

Každá vrstva jako plochý obdélník s výškou 18–22 mm. Backend vrstva #0B1F3A s bílým textem. AI worker vrstva s modrým horním pruhem. Data/storage neutrální #F5F7FA. Šipky jednoduché, #2E6BFF.

[CONTENT]

Produkt: systémové vrstvy

Mobilní aplikace  
Slouží jako vstup z terénu: založení nebo otevření zakázky, pořízení fotek, odeslání souborů a metadat, zobrazení základního stavu. Mobil nemá počítat cenu ani určovat finální rozsah.

Desktop Qt  
Kancelářské pracoviště pro kalkulanta nebo manažera. Qt klient umí pracovat se seznamem zakázek, detailem zakázky, fotkami, hlavní a referenční fotkou, proposal draftem, final proposalem, odesláním a workflow guardy. Desktop nemá být zdroj pravdy.

Backend API  
FastAPI backend je rozhodovací vrstva. Řeší autentizaci, tenant izolaci, projekty, fotky, katalog prací, workflow stav, výpočty, exporty, audit a integraci se storage.

Worker + AI  
Worker zpracovává asynchronní úlohy, drží lease, retry a DLQ model. AI provider vrací strukturovaný návrh: detekce, extrakce, mapování na katalog.

Data + Storage  
PostgreSQL drží autoritativní relační stav. Produkční soubory patří do S3-compatible storage; databáze ukládá storage keys, ne veřejné URL. Redis slouží pro runtime transport, cache a fronty, nikoli jako hlavní business pravda.

HIGHLIGHT BOX  
Architektura je navržená tak, aby selhání AI nebo fronty nezničilo datovou pravdu. AI výstup je důležitý návrh, ale autoritativní stav zakázky je serverový a databázový.

---

=== PAGE 7 ===

[LAYOUT]

12 sloupců. Horní část: třífázová AI pipeline přes 12 sloupců. Střed: vysvětlení `workTypeCode` ve dvou sloupcích 7/5. Spodní část: highlight box.

[DESIGN]

AI pipeline jako tři moduly s číslováním: Detection, Extraction, Mapping. Každý modul má horní linku #2E6BFF. `workTypeCode` sázet monospace 11 pt, akcent #2E6BFF. Highlight box dole.

[CONTENT]

Produkt: AI pipeline a `workTypeCode`

AI pipeline má tři vrstvy:

1. Detection  
Model identifikuje objekt, povrch, stav a případnou oblast zájmu. Výstupem může být typ objektu, stav povrchu, mask polygon a confidence.

2. Extraction  
Systém převádí detekci na normalizované údaje: odhad plochy, jednotku, doporučený rozsah, materiály, pracovní kroky, časovou náročnost a katalogové atributy.

3. Mapping  
Výstup se mapuje na katalog prací: `resolvedWorkTypeCode`, analysis profile, verzi profilu, primární množství a validační upozornění.

`workTypeCode` je core princip produktu. Je to stabilní strojový kód práce, který spojuje:
- globální katalog prací,
- tenant konfiguraci a cenové profily,
- projektové work items,
- AI vision detections,
- pricing a exportní výstupy.

Příklady kódů: `roof-repair`, `chimney-renovation`, `tile-installation`, `window-installation`, `electrical-installation`, `foundation-work`, `cleaning-after-construction`, `emergency-repair`.

HIGHLIGHT BOX  
Bez `workTypeCode` by AI výstup zůstal textovým doporučením. S `workTypeCode` se stává vstupem do řízeného workflow: parametrů, validací, tenant override pravidel, pricing profilu a auditovatelného výstupu.

---

=== PAGE 8 ===

[LAYOUT]

12 sloupců. H2 nahoře. Čtyři silné stránky jako 2×2 grid, každý blok přes 6 sloupců. Dole krátký callout přes 12 sloupců.

[DESIGN]

Každý blok má nadpis #0B1F3A a krátkou akcentní linku #2E6BFF. Žádné ikony nutné. Callout jako highlight box.

[CONTENT]

Silné stránky: jasně oddělené odpovědnosti

1. Server je zdroj pravdy  
Backend nefunguje jako pasivní proxy. Ověřuje vstupy, drží workflow stav, rozhoduje o povolených akcích, ukládá auditní stopu a generuje výstupy.

2. Klienti jsou pracovní rozhraní  
Mobil sbírá vstup, Qt desktop kontroluje a upravuje. Klient může navrhnout nebo odeslat změnu, ale server ji musí potvrdit.

3. AI nemá poslední slovo  
AI doporučuje rozsah, plochu, materiály a workflow kroky. Finální plocha, cena a návrh zůstávají pod kontrolou serveru a člověka.

4. Runtime je asynchronní  
Těžké úlohy mají patřit do workerů a front. To snižuje riziko, že AI volání, export nebo resize obrázků zablokuje běžnou práci v API.

HIGHLIGHT BOX  
Nejde pouze o čistotu architektury. Toto oddělení odpovědností snižuje právní, provozní i obchodní riziko: je jasné, kdo navrhl, kdo potvrdil a kde je uložen finální stav.

---

=== PAGE 9 ===

[LAYOUT]

12 sloupců. Levý blok přes 7 sloupců popisuje work catalog. Pravý blok přes 5 sloupců obsahuje highlight box a mini seznam guardů. Spodní část: tabulka entit.

[DESIGN]

Tabulka s tmavým záhlavím. Pravý blok neutrální pozadí #F5F7FA. Důležité entity sázet monospace.

[CONTENT]

Silné stránky: work catalog jako doménové jádro

Work catalog je první skutečně strategická doménová vrstva NOVU Builderu. Nejde o seznam položek v UI. Je to zdroj významu pro práci, parametry, tenant konfiguraci, vision výstupy a cenové profily.

Systém nepoužívá volné JSON blob struktury jako hlavní doménový model. Katalog prací je modelován relačně a explicitně: globální kategorie, work types, parametry, enum možnosti, analysis profiles, pricing profiles, tenant overrides, project work items a vision detections.

HIGHLIGHT BOX  
Tenant override model je delta-based. To znamená, že 100k tenantů nemusí znamenat 100k kopií katalogu. Tenant ukládá jen rozdíl proti globální definici.

COMPARISON TABLE

| Vrstva | Účel | Proč je důležitá |
|---|---|---|
| Global catalog | Kanonické definice prací | Jednotný jazyk systému |
| Tenant effective layer | Firemní odchylky | Přizpůsobení bez kopírování katalogu |
| Runtime work item | Stav práce v konkrétní zakázce | Audit a dlouhodobá správnost |
| Vision detection | Fakta z AI/obrazu | Re-play, odmítnutí, re-link bez ztráty historie |
| Pricing profile | Pravidla výpočtu | Vysvětlitelný cenový výstup |

---

=== PAGE 10 ===

[LAYOUT]

12 sloupců. Horní třetina: „provozní guardraily“ v textu. Střed: 3 highlight boxy vedle sebe přes 4+4+4 sloupce. Spodní část: krátká tabulka „Ověřitelnost“.

[DESIGN]

Highlight boxy s modrým levým pruhem. Tabulka jednoduchá, 10 pt. Použít #E63946 pouze pro text „není full enterprise ready“.

[CONTENT]

Silné stránky: provozní disciplína

NOVU Builder už obsahuje prvky, které často v raných SaaS produktech chybí: health a readiness endpointy, oddělení API readiness od processing readiness, audit log, rate limiting, worker heartbeat signály, retry budget, DLQ koncept, backpressure a produkční pravidlo, že local storage není autoritativní storage.

HIGHLIGHT BOX  
Fail-fast přístup: systém má při špatné konfiguraci nebo nedostupné kritické službě raději odmítnout start nebo operaci, než pokračovat v nejasném stavu.

HIGHLIGHT BOX  
Auditovatelnost: security-critical operace mají být zapsány do DB audit truth. Pokud audit selže, správné chování je fail-closed, ne tichý úspěch.

HIGHLIGHT BOX  
Testovatelnost: repo obsahuje rozsáhlou sadu testů pro tenant izolaci, auth, worker, storage, upload, workflow, query hardening a work catalog kontrakty.

COMPARISON TABLE

| Oblast | Stav | Hodnota |
|---|---|---|
| Tenant izolace | Implementovaná a testovaná | Chrání zákaznické hranice |
| Storage model | S3 jako produkční autorita | Snižuje riziko ztráty souborů |
| Queue model | Redis transport + DB job truth | Obnovitelnost po runtime výpadku |
| Monitoring | Široké metriky, část alertů vyžaduje doladění | Viditelnost bez falešné jistoty |
| Produkční verdikt | Řízený pilot, ne full enterprise ready | Realistická komunikace rizika |

---

=== PAGE 11 ===

[LAYOUT]

12 sloupců. Full-width comparison table. Nad tabulkou krátký kontext. Dole risk-neutral callout: „Nejde o přímou náhradu“.

[DESIGN]

Tabulka se třemi sloupci podle povinné struktury: Kategorie, Běžná řešení, NOVU Builder. Záhlaví #0B1F3A, akcentní slova #2E6BFF. Dole highlight box.

[CONTENT]

Srovnání s trhem: ChatGPT / Claude

ChatGPT a Claude jsou silné obecné AI asistenty. Umí pracovat s texty, soubory, obrázky, daty a rozsáhlým kontextem. V enterprise režimu nabízejí administraci, bezpečnostní prvky a týmové použití. Pro NOVU Builder jsou ale spíše AI infrastruktura nebo benchmark uživatelského očekávání než přímý produktový konkurent.

COMPARISON TABLE

| Kategorie | Běžná řešení | NOVU Builder |
|---|---|---|
| Primární účel | Obecná práce s textem, soubory, daty a obrazem | Řízené zpracování stavební/servisní zakázky |
| Doménový model | Prompt, projekt, soubor, konverzace | `workTypeCode`, work catalog, tenant konfigurace, workflow stav |
| Výstup | Odpověď, dokument, analýza, návrh | Auditovatelný podklad zakázky a cenový výstup |
| Odpovědnost | Uživatel interpretuje výsledek | Server validuje, člověk potvrzuje, systém ukládá historii |
| Pricing | Obecný výpočet v konverzaci | Pricing profily, pravidla, položky a audit výpočtu |
| Integrace do provozu | API nebo ruční práce v chatu | Produktový workflow od fotky po final proposal |

HIGHLIGHT BOX  
Obecná AI odpovídá na otázku. NOVU Builder spravuje stav zakázky. Rozdíl je zásadní: zákazník nekupuje jen inteligentní textový výstup, ale kontrolovaný proces.

---

=== PAGE 12 ===

[LAYOUT]

12 sloupců. Nadpis a úvod přes 12 sloupců. Střed: comparison table. Pravý spodní highlight box přes 5 sloupců, levý spodní text přes 7 sloupců.

[DESIGN]

Tabulka stejného stylu jako strana 11. Highlight box #F5F7FA. Zachovat vizuální konzistenci tržní sekce.

[CONTENT]

Srovnání s trhem: stavební software

Stavební platformy typu Procore nebo Autodesk Construction Cloud řeší široký stavební lifecycle: dokumenty, field-office spolupráci, RFIs, submittals, rozpočty, reporting, issue management, projektové řízení a integrace. Jejich síla je šířka platformy a enterprise adopce. NOVU Builder je užší a specializovanější: fotodokumentace → AI návrh → katalog práce → cenový podklad.

COMPARISON TABLE

| Kategorie | Běžná řešení | NOVU Builder |
|---|---|---|
| Rozsah | End-to-end construction management | Specializovaný tok pro fotky, analýzu a nabídku |
| Cílový uživatel | General contractor, owner, enterprise projektové týmy | Menší a střední firmy, servisní/stavební týmy, kalkulanti |
| Datový model | Projekt, dokumenty, úkoly, rozpočty, RFI | Zakázka, fotky, work items, AI detections, pricing profiles |
| AI role | Automatizace a insighty nad platformou | Analýza fotek a mapování na konkrétní work type |
| Nasazení | Velká platforma s širší změnou procesů | Užší produkt s rychlejším zavedením do nabídky/workflow |
| Odlišení | Šířka a integrace | Hloubka v konkrétním photo-to-offer procesu |

NOVU Builder se nemá prezentovat jako náhrada všech stavebních platforem. Silnější pozice je doplněk nebo specializovaná alternativa pro firmy, které nechtějí zavádět plný enterprise construction suite, ale potřebují zrychlit konkrétní tok od fotky k nabídce.

HIGHLIGHT BOX  
Nejlepší tržní pozice: úzký, auditovatelný systém pro opakované nabídky a servisní zakázky, ne obecný projektový ERP.

---

=== PAGE 13 ===

[LAYOUT]

12 sloupců. Vlevo text 5 sloupců o inspection apps. Vpravo comparison table 7 sloupců. Dole callout přes 12 sloupců.

[DESIGN]

Vpravo tabulka, vlevo čistý text. Callout s modrým pruhem. Udržet vysokou čitelnost, žádné zbytečné grafické prvky.

[CONTENT]

Srovnání s trhem: inspection apps

Inspection a punch-list aplikace řeší hlavně sběr zjištění v terénu, označení závad, fotky, úkoly, odpovědnosti, reporty a uzavření položek. To je blízké první polovině toku NOVU Builderu, ale obvykle to nekončí doménovým pricingem a návrhem nabídky.

COMPARISON TABLE

| Kategorie | Běžná řešení | NOVU Builder |
|---|---|---|
| Primární workflow | Inspekce, punch list, závady, report | Zakázka, analýza, práce, cena, final proposal |
| Fotky | Dokumentace a důkaz | Vstup do AI pipeline a katalogového mapování |
| Úkoly | Přiřazení a sledování odstranění závad | Work item s parametry, confirmation stavem a pricing vazbou |
| Report | PDF report inspekce | Cenový a obchodně použitelný podklad |
| AI | Volitelná pomoc nebo summarizace | Strukturovaná vision pipeline s provider kontraktem |
| Silná stránka | Terénní koordinace | Přemostění mezi technickou fotkou a nabídkou |

HIGHLIGHT BOX  
NOVU Builder má největší hodnotu tam, kde nestačí závadu jen zaznamenat. Firma potřebuje z fotky odvodit typ práce, množství, materiál, pracovní postup, cenu a výstup pro zákazníka.

---

=== PAGE 14 ===

[LAYOUT]

12 sloupců. H2 nahoře. Velký centrální diagram „workTypeCode jako páteř“ přes 12 sloupců. Pod diagramem čtyři krátké vysvětlující bloky.

[DESIGN]

Centrální pojem `workTypeCode` v rámečku #0B1F3A s bílým textem. Z něj čtyři linky #2E6BFF do bloků: AI, katalog, tenant, pricing/export. Bloky bílé s linkou #D7DDE8.

[CONTENT]

Odlišení: `workTypeCode` jako páteř systému

`workTypeCode` je produktové odlišení, protože převádí nejasný AI výstup do kontrolovaného doménového systému. Umožňuje, aby jedna práce měla stabilní identitu napříč UI, backendem, AI pipeline, ceníkem, výpočtem i historií zakázky.

AI  
AI vrátí návrh typu práce, množství, stavu a atributů. Bez katalogového mapování je to jen doporučení.

Katalog  
Globální katalog definuje parametry, jednotky, povinná pole, typy hodnot a profil analýzy.

Tenant  
Firma může práci povolit, přejmenovat, změnit výchozí hodnoty, připojit svůj pricebook nebo přidat řízené extra parametry.

Pricing a export  
Výpočet se neopírá jen o text. Používá strukturované položky, pricing profily, pravidla a auditní snapshot.

HIGHLIGHT BOX  
Toto je bariéra proti komoditizaci. Samotná vision AI bude stále dostupnější. Stabilní doménový model, validace, tenant override a audit historie jsou část, která tvoří dlouhodobější hodnotu produktu.

---

=== PAGE 15 ===

[LAYOUT]

12 sloupců. Dva sloupce 6/6. Vlevo odlišení pro zákazníka, vpravo odlišení pro investora. Dole full-width comparison table.

[DESIGN]

Vlevo highlight box, vpravo bílý blok s akcentní linkou. Tabulka standardní. Výraz „ne“ v červené nepoužívat agresivně; dokument má zůstat profesionální.

[CONTENT]

Odlišení: proč je produkt obhajitelný

Pro zákazníka  
NOVU Builder neslibuje, že AI bez kontroly nahradí kalkulanta. Nabízí praktičtější hodnotu: rychlejší přípravu podkladu, menší ztrátu informací mezi terénem a kanceláří, jednotnější postup a dohledatelnou historii.

Pro investora  
Produkt má potenciál růst přes doménovou specializaci, nikoli přes nákladný závod s obecnými AI asistenty. Hodnota se kumuluje v katalogu prací, workflow datech, pricing pravidlech, tenant konfiguracích a opakovaném používání.

COMPARISON TABLE

| Kategorie | Běžná řešení | NOVU Builder |
|---|---|---|
| AI výstup | Textový návrh nebo shrnutí | Strukturovaný vstup do workflow |
| Kontrola | Ruční interpretace uživatelem | Confirmation/correction stav v systému |
| Historie | Často mimo hlavní tok | Auditní a runtime záznamy u zakázky |
| Adaptace na firmu | Nastavení šablon nebo promptů | Tenant override nad katalogem prací |
| Dlouhodobá hodnota | Závislost na platformě | Vlastní doménový model a data |

HIGHLIGHT BOX  
Nejsilnější positioning: NOVU Builder je operační systém pro opakované nabídky nad fotodokumentací, ne nástroj pro jednorázové AI odpovědi.

---

=== PAGE 16 ===

[LAYOUT]

12 sloupců. Roadmapa 0–6 měsíců jako čtyři horizontální pásy. Každý pás: cíl, konkrétní kroky, měřitelný výstup. Dole risk-aware highlight box.

[DESIGN]

Pásy oddělené linkou #D7DDE8. Čísla fází v #2E6BFF. Dole highlight box. Žádné časové sliby v marketingovém stylu.

[CONTENT]

Budoucí rozvoj: nejbližší produktová fáze

1. Stabilizace pilotního provozu  
Cíl: uzavřít provozní rizika, která by mohla zkreslit pilot.  
Kroky: zapnout a ověřit worker heartbeat, srovnat alert matematiku, zpřesnit readiness semantiku, ověřit storage policy, provést restore drill.  
Výstup: pilotní prostředí s jasným runbookem a měřitelným processing stavem.

2. Dokončení photo-to-offer workflow  
Cíl: dostat hlavní uživatelský tok do opakovatelné podoby.  
Kroky: upload, reference photo, analysis job, work item review, proposal draft, final proposal, export a send guard.  
Výstup: zákazník může projít tok od fotky po návrh nabídky bez ručního obcházení systému.

3. Rozšíření work catalogu  
Cíl: pokrýt více typů prací a parametrů.  
Kroky: doplnit katalogové seed definice, pricing profily, analysis profile bindings a UI pro rychlý výběr práce.  
Výstup: produkt není vázán na jednu ukázkovou práci.

4. UX polish Qt desktopu  
Cíl: snížit tření pro kalkulanta.  
Kroky: detail zakázky, foto viewer, overlay korekce, workflow stav, chybové stavy, finální potvrzení.  
Výstup: desktop je pracovní nástroj, ne jen technický prototyp.

HIGHLIGHT BOX  
Správná priorita není přidat co nejvíce funkcí. Správná priorita je uzavřít jeden tvrdý workflow tak, aby šel opakovaně předvést a měřit.

---

=== PAGE 17 ===

[LAYOUT]

12 sloupců. Levá část 7 sloupců: roadmapa 6–18 měsíců. Pravá část 5 sloupců: investiční logika a měřítka. Dole tabulka „milník / důkaz“.

[DESIGN]

Pravý panel jako highlight box. Tabulka standardní. Akcenty #2E6BFF pro měřitelné důkazy.

[CONTENT]

Budoucí rozvoj: produktová a tržní expanze

V horizontu 6–18 měsíců má NOVU Builder růst ve třech směrech: větší katalog prací, hlubší provozní spolehlivost a lepší integrace do zákaznického procesu.

Produktové směry:
- tenant-specific pricebooks a katalogové override UI,
- více AI providerů a provider capability registry,
- provider circuit breaker a quota guardy,
- exportní šablony pro různé typy zákazníků,
- integrační API pro CRM, účetnictví nebo stavební platformy,
- dashboard pro backlog, kvalitu AI, čas do nabídky a konverzi.

HIGHLIGHT BOX  
Investor by neměl měřit jen počet funkcí. Důležitější metriky jsou: čas od uploadu k návrhu, procento AI návrhů přijatých bez velké korekce, podíl zakázek dokončených do final proposal a opakované používání u jednoho tenanta.

COMPARISON TABLE

| Milník | Důkaz |
|---|---|
| Pilot s reálnými zákazníky | Zakázky dokončené od fotek po final proposal |
| Stabilní AI pipeline | Měřené confidence, korekce a false-positive rate |
| Širší katalog prací | Více workTypeCode s validovanými parametry a pricing profily |
| Provozní zralost | Restore drill, alerty, runbooky, load rehearsal |
| Komerční připravenost | Opakovatelné onboarding kroky a jasné balíčky |

---

=== PAGE 18 ===

[LAYOUT]

12 sloupců. H2 nahoře. Tři risk boxy přes 4+4+4 sloupce. Dole mitigation tabulka přes 12 sloupců.

[DESIGN]

Risk boxy s #E63946 levým pruhem a pozadím #FFF4F5. Mitigation tabulka se záhlavím #0B1F3A. Rizika psát konkrétně, bez dramatizace.

[CONTENT]

Rizika: produkt a trh

RISK BOX  
Riziko 1: zákazník očekává magickou AI  
Pokud bude produkt prezentován jako plně autonomní kalkulant, vznikne nedůvěra při první korekci. Správný framing je AI-assisted workflow s lidským potvrzením.

RISK BOX  
Riziko 2: stavební týmy mění proces pomalu  
Firmy často pracují přes telefon, e-mail, WhatsApp a tabulky. Produkt musí řešit reálné tření: jednoduchý sběr, rychlý review a minimum administrativy.

RISK BOX  
Riziko 3: velké platformy mohou přidat podobné AI funkce  
Procore, Autodesk nebo inspekční nástroje mohou posílit AI nad fotkami. NOVU Builder musí stavět na doménové hloubce, rychlosti nasazení a workType/pricing vrstvě.

COMPARISON TABLE

| Riziko | Dopad | Mitigace |
|---|---|---|
| Přestřelený AI positioning | Zklamání zákazníka | Prezentovat AI jako návrh, ne autoritu |
| Pomalá adopce | Nízké používání | Začít jedním tvrdým workflow a jasným ROI |
| Konkurence platforem | Tlak na cenu a pozici | Specializace, integrace, rychlejší produktová iterace |
| Nejednotné vstupy z terénu | Horší kvalita výstupu | Foto checklist, reference photo, confidence a ruční korekce |
| Nejasný buyer | Dlouhý sales cyklus | Cílit kalkulanty, servisní týmy a menší stavební firmy |

---

=== PAGE 19 ===

[LAYOUT]

12 sloupců. Čtyři risk boxy jako 2×2 grid. Dole krátký „realistický verdikt“ v highlight boxu.

[DESIGN]

Risk boxy s červeným akcentem. Highlight box modrý. Nepoužívat velké červené plochy; rizika mají být čitelná, ne alarmistická.

[CONTENT]

Rizika: technika a provoz

RISK BOX  
AI přesnost a odpovědnost  
Špatná fotka, malý počet úhlů nebo nejasný rozsah může vést k chybnému odhadu plochy či materiálu. Mitigace: confidence score, reference photo, ruční korekce, audit toho, kdo finální hodnotu potvrdil.

RISK BOX  
Load profil  
Analýzy, exporty a photo processing jsou těžké operace. Bez zapnuté heavy lane a dostatečné worker concurrency může růst zatížit API a prodloužit odezvy.

RISK BOX  
Redis failure isolation  
Redis nemá být business source of truth, ale je kritický runtime dependency. Je nutné oddělit role auth, queue a cache nebo alespoň sjednotit klientský kontrakt a recovery invarianty.

RISK BOX  
Monitoring drift  
Metriky existují, ale alert matematika, probe dokumentace a dashboardy musí odpovídat realitě. Jinak systém může mít data, ale operátor neuvidí správný význam.

HIGHLIGHT BOX  
Realistický verdikt: současná architektura nevyžaduje restart. Vyžaduje disciplinovaný hardening: heavy lane, alerty, restore drill, Redis role separation, tenant caps a pravidelné load rehearsals.

---

=== PAGE 20 ===

[LAYOUT]

12 sloupců. Horní text přes 12 sloupců. Střed: 2 sloupce 6/6 „Security“ a „Stability“. Dole tabulka bezpečnostních principů.

[DESIGN]

Security sloupec s #0B1F3A horní linkou, Stability sloupec s #2E6BFF horní linkou. Tabulka standardní. Používat přesné termíny: fail-fast, fail-closed, DB truth, signed URL, readiness.

[CONTENT]

Bezpečnost + stabilita

Bezpečnost NOVU Builderu stojí na tom, že kritická rozhodnutí nejsou ponechána klientovi ani AI provideru. Autentizace, tenant hranice, workflow akce, audit, storage politika a final proposal patří na backend.

Security  
Systém používá tenant izolaci, JWT/session model, token invalidaci, audit log, rate limiting, upload validaci a bezpečnostní guardy pro admin a auth operace. Security-critical audit má být vynucený: pokud se auditní zápis nepovede, operace nemá tiše projít.

Stability  
Stabilita je založená na oddělení API plane a processing plane. API může být dostupné pro čtení, i když zpracování AI jobů je degradované, ale readiness musí tento rozdíl explicitně ukázat. Worker používá lease, retry a DLQ model, aby selhání nebylo neviditelné.

COMPARISON TABLE

| Princip | Implementační význam | Business význam |
|---|---|---|
| Fail-fast | Špatná konfigurace zastaví start nebo operaci | Menší riziko skryté nekonzistence |
| Fail-closed | Kritická ochrana nesmí být tiše obejita | Vyšší důvěra zákazníka |
| DB truth | Tokeny, audit a job lifecycle jsou autoritativně v DB | Obnovitelnost po runtime výpadku |
| Signed URL | Storage nevystavuje trvalé veřejné odkazy | Nižší riziko úniku souborů |
| Audit trail | Akce a změny jsou dohledatelné | Odpovědnost a forenzní čitelnost |
| Processing readiness | Worker/fronta mají vlastní stav | Lepší incident řízení |

HIGHLIGHT BOX  
Bezpečnostní message pro zákazníka: NOVU Builder neprodává „AI rozhodnutí“. Prodává kontrolovaný proces, kde AI návrh prochází validací, korekcí, uložením a auditní stopou.

---

=== PAGE 21 ===

[LAYOUT]

12 sloupců. Horní část: realistický scaling statement. Střed: tři úrovně škálování v horizontálních pásech. Dole tabulka 100k+ požadavků.

[DESIGN]

Pásy: Pilot, Growth, 100k+; každý s jiným horním akcentem #2E6BFF, bez změny dominantní palety. Tabulka standardní. Červenou použít jen pro varování „neaktuální kapacita“.

[CONTENT]

Škálování

100k+ klientů je správný architektonický cíl, ale nesmí být komunikován jako dnešní ověřená kapacita. Dnešní systém má některé správné základy: stateless API směr, PostgreSQL jako zdroj pravdy, Redis fronty, worker model, bounded queues, tenant-effective katalog a delta-based overrides. Pro 100k+ účtů je ale nutný další infrastrukturní a provozní vývoj.

Pilot  
5–10 tenantů, řízený onboarding, měřené workflow, manuálně sledované incidenty, ověřený restore drill.

Growth  
50–500 tenantů, zapnutá heavy lane, worker concurrency 2–4+, per-tenant caps, monitoring dashboardy, alerty, SLO, oddělené Redis role.

100k+  
Stateless API repliky, horizontální worker pooly, Redis Sentinel/Cluster nebo oddělené managed služby, DB pooling, read replicas, partitioning nebo sharding podle růstu, object storage s jasnou lifecycle politikou, tenant-aware quotas, AI provider circuit breakers a smluvně zajištěná kapacita upstream providerů.

COMPARISON TABLE

| Oblast | Minimum pro růst | 100k+ cílový princip |
|---|---|---|
| API | Více instancí za load balancerem | Stateless horizontální škálování |
| DB | Pooling a indexy hot paths | HA, read replicas, partitioning, případně sharding |
| Redis | Oddělit auth/queue/cache role | Cluster/failover, jasné failure domains |
| Worker | Concurrency a heavy lane | Elastický worker pool podle queue age |
| Storage | S3 authoritative, signed URL | Lifecycle, regionální strategie, cost controls |
| Tenant fairness | Per-tenant caps | Quotas, billing, noisy-neighbor ochrana |
| AI | Retry a timeouty | Circuit breaker, provider routing, kapacitní kontrakty |

RISK BOX  
Největší škálovací riziko není databáze samotná. Je to kombinace těžkých operací, AI latence, exportů, uploadů a nedostatečné tenant fairness. Tyto oblasti musí být měřené dřív, než začne agresivní růst.

---

=== PAGE 22 ===

[LAYOUT]

12 sloupců. Horní závěr přes 8 sloupců. Pravý summary box přes 4 sloupce. Střed: „co říkat investorům / zákazníkům“ ve dvou sloupcích. Spodní finální statement přes 12 sloupců.

[DESIGN]

Závěr H2 #0B1F3A. Pravý summary box jako highlight box. Střední dva sloupce oddělit tenkou svislou linkou #D7DDE8. Spodní statement v #0B1F3A boxu s bílým textem.

[CONTENT]

Závěr

NOVU Builder má technicky obhajitelný základ pro řízený pilot a produktovou prezentaci. Nejsilnější částí není samotná AI analýza, ale schopnost vložit AI do kontrolovaného doménového workflow: od fotky přes `workTypeCode`, validace, tenant konfiguraci, lidské potvrzení, pricing pravidla a auditní historii až k finálnímu výstupu.

HIGHLIGHT BOX  
Doporučený verdikt: připravené pro pilot a obchodní ověření, neprezentovat jako hotový hyperscale enterprise systém. Silná stránka je architektura, transparentní rizika a jasná cesta k hardeningu.

Co říkat investorům  
NOVU Builder staví vrstvu, která převádí obecné AI schopnosti do doménového, opakovatelného a auditovatelného procesu. Investiční hodnota je v katalogu prací, datovém modelu, workflow historii, tenant konfiguraci a schopnosti škálovat specializovaný use case.

Co říkat zákazníkům  
NOVU Builder nezbavuje firmu kontroly nad nabídkou. Zrychluje přípravu podkladů, snižuje chaos mezi terénem a kanceláří a dává týmu jasné místo, kde se návrh ověřuje, upravuje a schvaluje.

Finální statement  
NOVU Builder je systém pro řízenou tvorbu technických a cenových podkladů nad fotodokumentací. Jeho hodnota stojí na spojení AI, katalogu prací, backendové pravdy, desktopové kontroly a auditovatelného provozu.

