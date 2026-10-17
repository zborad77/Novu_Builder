# NOVU Builder

## Inteligentní systém pro analýzu stavebních zakázek pomocí AI

NOVU Builder je produktový a technický systém pro převod fotodokumentace stavebních zakázek do strukturovaného workflow, návrhu prací a cenového podkladu. Je navržen pro firmy, které potřebují rychleji zpracovat velké množství případů, ale zároveň nesmí ztratit kontrolu nad rozhodnutím, cenou, auditní stopou a datovou konzistencí.

Dokument hodnotí projekt jako kombinaci investiční příležitosti, produktové prezentace a technického auditu. Stav odpovídá řízenému pilotu a near-production foundation, ne hotovému hyperscale enterprise produktu.

Datum dokumentu: 29. dubna 2026  
Určeno pro: investory, zákazníky, produktové a technické partnery  
Hodnocený projekt: NOVU Builder

---

# 1. Titulní strana

## NOVU Builder

### Inteligentní systém pro analýzu stavebních zakázek pomocí AI

NOVU Builder propojuje terénní fotodokumentaci, kancelářskou kontrolu, backendovou logiku a AI pipeline do jednoho řízeného procesu. Cílem není pouze získat odpověď od modelu, ale vytvořit auditovatelný pracovní tok od fotografie přes typ práce až po cenový podklad.

Projekt má potenciál zejména tam, kde se dnes zakázky zpracovávají ručně: fotky v telefonu, poznámky v chatu, odhady v tabulce a nabídka tvořená individuální zkušeností kalkulanta. NOVU Builder tento proces strukturuje, zrychluje a dává mu opakovatelné technické jádro.

**Shrnutí**

NOVU Builder je praktický systém pro stavební a servisní firmy, které potřebují převést obrazová data a popis zakázky do konkrétního návrhu práce, parametrů, cenového výpočtu a finálního výstupu. Hodnota produktu stojí na spojení AI, katalogu prací, backendového source of truth a lidské kontroly.

---

# 2. Executive Summary

## Co projekt řeší

Ve stavebních a servisních firmách vzniká velká část obchodní a technické práce z neúplných vstupů: fotek, krátkých popisů, telefonátů a individuální zkušenosti pracovníka. Tento stav je funkční v malém měřítku, ale špatně se škáluje. S rostoucím počtem zakázek roste chybovost, zpoždění, nejednotnost odhadů a obtížnost zpětně zjistit, proč byla nabídka vytvořena právě takto.

NOVU Builder tento problém řeší jako **photo-to-workflow-to-offer** systém. Vstupem jsou fotografie a metadata zakázky. Systém je validuje, uloží, analyzuje pomocí AI, mapuje na konkrétní typ práce, umožní člověku výsledek ověřit a připraví strukturovaný cenový podklad.

## Pro koho je určen

Primární cílová skupina nejsou obecní uživatelé AI. Produkt je určen pro firmy, které pravidelně zpracovávají technické zakázky nad fotodokumentací:

- stavební a rekonstrukční firmy,
- servisní a údržbové týmy,
- firmy řešící střechy, fasády, okna, zdivo, interiéry nebo havarijní opravy,
- kalkulanti a office manažeři,
- partneři s více pobočkami nebo větším počtem terénních pracovníků.

## V čem je zásadní hodnota

Zásadní hodnota není jen v použití AI nad fotografií. Takovou schopnost budou postupně nabízet obecné modely i velké platformy. Hodnota NOVU Builderu je v tom, že AI výstup převádí do **doménového modelu**, konkrétně do katalogu prací, parametrů, workflow stavů, cenových pravidel a auditní historie.

Jádrem tohoto přístupu je **workTypeCode**. Tento strojový kód reprezentuje konkrétní typ práce a spojuje AI detekci, katalog, tenant nastavení, projektový work item, pricing profil a exportní výstup. Díky tomu systém nepracuje jen s textem, ale s daty použitelnými pro další akce.

## Proč je projekt relevantní

Trh se posouvá dvěma směry. Na jedné straně existují obecné AI nástroje, které umí analyzovat texty, soubory i obrázky. Na druhé straně existují robustní stavební platformy, které řídí projekty, dokumenty, rozpočty a terénní spolupráci. Mezi nimi je prostor pro užší produkt, který řeší konkrétní bolest: rychlejší a přesnější převod fotodokumentace do nabídky.

**Klíčové body**

- Projekt řeší konkrétní provozní problém, ne abstraktní AI experiment.
- AI je součást workflow, ne samostatná konverzace.
- Backend je zdroj pravdy pro zakázky, stav, výpočty a audit.
- Produkt má realistickou pilotní hodnotu a jasnou cestu k hardeningu.
- Největší diferenciace je v doménovém work-type systému.

---

# 3. Původní záměr vs aktuální směr

## Původní záměr

Původní záměr projektu byl ověřit, zda lze z fotek stavební situace rychle vytvořit návrh cenové nabídky. Projekt byl koncipován jako prototyp, který měl ukázat produktový tok: nahrání fotek, základní analýza, odhad rozsahu, návrh prací a příprava nabídky.

Tento přístup měl správnou hodnotu pro první fázi. Pomohl ověřit, že existuje uživatelský problém, že fotografie jsou důležitý vstup a že firma může získat praktickou hodnotu z rychlejšího zpracování zakázky. Zároveň ukázal, že samotná AI odpověď nestačí. Aby byl výstup použitelný obchodně, musí být zasazen do strukturovaného procesu.

Původní koncepce byla blíže prototypu kancelářského nástroje. Důraz byl na rychlé ověření nápadu, datový model, základní workflow a první podobu návrhu nabídky. Technologicky šlo o fázi, kde se ještě hledal cílový runtime a hranice mezi klientem, serverem a AI.

## Aktuální záměr

Aktuální směr je výrazně silnější. Projekt se posunul k architektuře, kde je **desktop aplikace v Qt** pracovním rozhraním pro člověka, **backend ve FastAPI** je centrální autoritou a **AI pipeline** je specializovaná návrhová vrstva.

Nový směr obsahuje jasné rozdělení odpovědností:

- mobil nebo terénní vstup sbírá data,
- desktop kontroluje, upravuje a schvaluje,
- backend validuje, ukládá, rozhoduje a počítá,
- AI navrhuje, klasifikuje a extrahuje,
- databáze drží autoritativní stav,
- fronty a worker zpracovávají pomalé úlohy mimo běžný request.

Tento posun mění projekt ze samotného nástroje pro tvorbu nabídky na **platformní workflow pro řízení zakázky**. To je strategicky důležité, protože cenová nabídka je pouze jeden výstup. Dlouhodobá hodnota je v datech, historii, katalogu prací, konfiguraci firem a opakovatelném procesu.

## Co se změnilo strategicky

Strategická změna spočívá ve třech bodech.

První změna je přesun od volného AI výstupu ke strukturovanému výstupu. Systém nechce jen vygenerovat text, ale vytvořit stav, položky, parametry a výpočet.

Druhá změna je přesun business logiky na backend. Klient nemá být zdroj pravdy. Klient má zobrazit stav a umožnit uživateli akci, ale server musí rozhodnout, zda je akce povolená a jak se propíše do dat.

Třetí změna je škálování přes katalog a fronty. Pokud má systém zvládat velké množství zakázek, nemůže být každý typ práce řešen ad hoc promptem nebo větvením v UI. Musí existovat katalog, kódy, profily, validace a auditní snapshoty.

## Proč je nový směr silnější

Nový směr je silnější, protože snižuje riziko chaosu. AI systém bez workflow může vytvořit přesvědčivý text, ale nemusí být dohledatelné, odkud se vzala čísla, kdo je potvrdil, jaký ceník se použil a zda se výsledek vztahuje ke správné firmě.

NOVU Builder se snaží vybudovat systém, ve kterém je každý důležitý krok pojmenovaný. Fotka má storage key. Zakázka má stav. AI job má lifecycle. Work item má workTypeCode. Hodnota má zdroj, confidence a confirmation stav. Cenová položka má pravidlo a profil.

**Shrnutí**

Původní záměr ověřil potřebu. Aktuální směr vytváří produkt, který může nést reálný provoz. To je rozdíl mezi prototypem a systémem, který lze postupně nabídnout zákazníkům.

---

# 4. Produkt - co NOVU Builder dělá

## Analýza fotografií staveb

NOVU Builder přijímá fotodokumentaci zakázky a používá ji jako hlavní vstup pro další zpracování. Fotografie nejsou jen příloha k případu. Jsou technickým důkazem, vstupem pro AI analýzu a podkladem pro lidskou kontrolu.

Systém počítá s tím, že fotografie mohou mít různou kvalitu. Proto je důležitá kombinace AI odhadu, confidence score, referenční fotky a ruční korekce. U stavebních zakázek je chybné tvrdit, že jeden model vždy spolehlivě určí plochu nebo rozsah. Správný produktový přístup je AI návrh plus kontrolované potvrzení.

## AI detekce problémů

AI vrstva má detekovat typ objektu, stav povrchu, poškození, rozsah, případnou oblast opravy a základní atributy. Typické domény zahrnují fasády, střechy, konstrukce, zdivo, interiéry, okna, komíny, základy nebo havarijní zásahy.

Pipeline není navržena jako jedno neprůhledné volání. Směr projektu počítá s etapami:

- **Detection** - co je na fotografii a kde je problém.
- **Extraction** - jaké jsou měřitelné parametry, materiály a pracovní kroky.
- **Mapping** - jak se výstup napojí na katalog prací a workTypeCode.

Tento model je důležitý, protože umožňuje auditovat, která část selhala. Pokud AI správně najde poškození, ale špatně ho namapuje na typ práce, je to jiný problém než špatná detekce obrazu.

## Návrh řešení přes work types

Výsledkem analýzy nemá být pouze věta typu "fasáda vyžaduje opravu". Produkt musí určit, o jaký typ práce jde, jaké parametry jsou potřeba a jaké kroky mají následovat.

Proto je v projektu zásadní vlastní work-type systém. Každý typ práce má stabilní kód, parametry, jednotky, sekce, validační pravidla a vazby na analýzu a pricing. Příkladem může být oprava střechy, renovace komínu, montáž oken, elektroinstalace nebo čištění po stavbě.

## Tvorba cenových nabídek

NOVU Builder směřuje k tomu, aby z potvrzeného work itemu vytvořil cenový podklad. Ten může zahrnovat práci, materiál, doplňkové náklady, varianty a export do dokumentu.

Důležité je, že cena nemá vznikat pouze jako textová odpověď AI. Cena má být vypočtena nad strukturovanými vstupy, ceníkem, pravidly a tenant konfigurací. To zvyšuje vysvětlitelnost a umožňuje firmě kontrolovat vlastní marži a cenovou politiku.

## Strukturování zakázek a práce s cases

Projekt pracuje s konceptem zakázky nebo case. Case drží informace o projektu, fotkách, analýzách, pracovních položkách, návrzích, exportech a workflow stavu.

To je důležité pro provoz. Firma nepotřebuje jen jednorázovou odpověď. Potřebuje seznam případů, stav každého případu, historii, kdo co změnil, které fotky jsou referenční, zda vznikl final proposal a zda je možné zakázku odeslat.

## Architektura srozumitelně

**Desktop aplikace v Qt** je kancelářské pracovní prostředí. Slouží k tomu, aby kalkulant nebo manažer viděl zakázky, fotografie, návrhy, stav workflow a mohl potvrdit nebo upravit výsledek. Desktop nemá nést hlavní business logiku.

**Backend service** je centrální autorita. Validuje vstupy, řeší autentizaci, tenant izolaci, stav zakázky, katalog prací, analýzy, výpočty, exporty a audit. Backend je místo, kde má být rozhodnutí, zda je akce povolená a jak se propíše do dat.

**AI pipeline** je samostatná návrhová vrstva. Přijímá projekt a fotky, vrací strukturovaný výstup a nemá poslední slovo nad cenou ani finální podobou nabídky.

**Data flow** začíná u vstupu z terénu nebo desktopu. Backend uloží metadata a soubory, založí nebo aktualizuje case, vytvoří analysis job, worker zavolá AI provider, výsledek se uloží do databáze, namapuje se na workTypeCode a uživatel jej zkontroluje v klientovi.

**Klíčové body**

- Produkt převádí fotky na řízené zakázkové workflow.
- AI výstup je strukturovaný a použitelný pro další akce.
- Backend drží business pravdu.
- Desktop slouží jako kontrolní a schvalovací pracoviště.
- Cases umožňují práci s velkým množstvím zakázek.

---

# 5. Hlavní silné stránky

## AI-first přístup: vision + decision support

AI-first zde neznamená, že AI autonomně rozhoduje. Znamená to, že produkt je od začátku navržen tak, aby obrazová analýza byla přirozenou součástí workflow.

AI má pomoci identifikovat problém, navrhnout rozsah, odhadnout plochu, doporučit materiály a připravit pracovní kroky. Rozhodnutí však musí zůstat validované systémem a potvrzené člověkem.

Dopad je praktický: firma může zkrátit čas prvního odhadu, ale zároveň neztrácí kontrolu nad odpovědností. To je pro stavební zakázky důležité, protože chyba v rozsahu nebo ploše má přímý finanční dopad.

## Strukturovaný výstup, ne jen text

Mnoho AI nástrojů skončí u textové odpovědi. Ta může být užitečná, ale obtížně se z ní staví provozní systém. NOVU Builder se liší tím, že výstup má být datový: typ práce, parametry, jednotky, confidence, materiály, pracovní kroky, validační upozornění a vazby na cenový profil.

To umožňuje automatizovat další kroky bez ztráty kontroly. Systém může zobrazit rozpracovanou položku, vyžádat povinný parametr, označit nízkou důvěru AI odhadu nebo zabránit odeslání nabídky bez final proposal.

## Škálovatelnost

Projekt je navržen tak, aby se mohl posouvat směrem k velkému počtu klientů a zakázek. Důležité prvky jsou multi-tenant model, backend jako samostatná služba, PostgreSQL jako relační source of truth, Redis pro fronty a runtime transport, worker pro asynchronní úlohy a S3-compatible storage pro soubory.

Cíl 100k+ klientů je relevantní jako architektonický směr, ne jako dnešní ověřená kapacita. Aby byl dosažitelný, bude nutné doplnit infrastrukturu, tenant fairness, horizontální worker pooly, oddělené Redis role, databázové škálování a provozní metriky.

Důležité je, že současný směr neblokuje budoucí růst. Největší hodnota je v tom, že systém se neupíná k lokálním souborům, klientské logice nebo jednomu neauditovatelnému runtime.

## Domain-specific intelligence

Obecná AI může popsat fotografii. NOVU Builder má ambici rozumět konkrétnímu stavebnímu procesu: jaký typ práce se řeší, které parametry jsou povinné, jaký materiál může být relevantní, co má kalkulant potvrdit a jak se výsledek použije v nabídce.

Tato doménová vrstva je klíčová. Je to místo, kde vzniká produktová obranyschopnost proti komoditizaci AI modelů. Pokud bude každý model umět "vidět" fotografii, výhoda bude v tom, kdo umí výsledek správně připojit k firemnímu workflow.

## Kombinace desktop + cloud

Qt desktop dává smysl pro kancelářskou práci, kde uživatel potřebuje přehled, rychlou práci s detaily, fotkami, návrhy a schvalováním. Cloud/backend vrstva zase řeší data, výpočty, storage, audit, fronty a integrace.

Tato kombinace může být silná v B2B prostředí. Uživatel dostane pracovní nástroj, který není jen webová stránka s formulářem, ale zároveň firma nezůstává u lokálních dat bez centrální kontroly.

## Vlastní work-type systém

Work-type systém je hlavní tahoun projektu. Dává produktu pevný slovník. Místo aby každá zakázka byla volný text, systém pracuje s kódy a parametry.

Co to znamená:

- práce má stabilní identitu,
- parametry mají typy a jednotky,
- tenant může dělat řízené odchylky,
- AI výstup lze mapovat na konkrétní práci,
- pricing může používat pravidla,
- audit může uchovat snapshot rozhodnutí.

Pro investora je to důležité, protože work-type systém je dlouhodobé aktivum. Pro zákazníka je to důležité, protože zvyšuje konzistenci výstupů a snižuje závislost na jednom zkušeném člověku.

**Shrnutí**

Tahouny projektu nejsou jednotlivé obrazovky. Jsou to principy: AI jako návrhová vrstva, strukturovaná data, backendová autorita, workTypeCode, tenant konfigurace a workflow kontrola.

---

# 6. Srovnání s jinými řešeními na trhu

## Obecné AI nástroje: ChatGPT, Claude

Obecné AI nástroje umí analyzovat text, pracovat se soubory, interpretovat obrázky, vytvářet dokumenty a pomáhat s rozhodováním. V enterprise variantách přidávají správu uživatelů, bezpečnostní prvky, analytiku používání a integrace.

Kde končí: obecný AI nástroj obvykle nezná interní katalog prací firmy, neřídí stav stavební zakázky, nevynucuje pricing pravidla, neudržuje auditní snapshot výpočtu a sám o sobě negarantuje, že výstup projde konkrétním workflow od fotky po nabídku.

**Srovnání**

ChatGPT nebo Claude mohou pomoci popsat fotku nebo navrhnout text. NOVU Builder má tento výstup převést do work itemu, parametrů, cenového modelu a schvalovacího procesu. Rozdíl je mezi odpovědí a provozním systémem.

## Stavební software a rozpočtové nástroje

Stavební software často řeší rozpočty, položkové ceníky, projektové řízení, dokumenty, reporting, úkoly, RFIs, submittals nebo komunikaci mezi kanceláří a stavbou. Silné platformy mají šířku, integrace a zavedené procesy.

Kde končí: mnoho těchto nástrojů není optimalizováno na rychlý převod běžné fotodokumentace malé nebo střední zakázky do AI asistovaného návrhu práce a nabídky. Mohou být robustní, ale zavedení bývá těžší a workflow může být příliš široké pro konkrétní photo-to-offer use case.

**Srovnání**

NOVU Builder nemá nahrazovat celý stavební ERP nebo enterprise construction suite. Je silnější jako specializovaný systém pro opakované nabídky, servisní zásahy a zakázky, kde fotografie a rychlý odhad hrají centrální roli.

## Photo inspection apps

Photo inspection a punch-list aplikace umí sbírat fotky, označovat závady, vytvářet úkoly, přiřazovat odpovědnosti a generovat reporty. Jsou velmi praktické pro terénní dokumentaci, kontrolu a uzavírání položek.

Kde končí: typicky nekončí doménovým pricingem, katalogovým workTypeCode modelem a tvorbou obchodní nabídky. Zaznamenají problém, ale nemusí ho převést do strukturované práce, materiálů, variant a cen.

**Srovnání**

Inspection app odpovídá na otázku "co je špatně a kdo to má opravit". NOVU Builder má odpovědět také na otázku "jaký typ práce z toho vzniká, jaké parametry jsou potřeba, kolik to může stát a jaký dokument pošleme zákazníkovi".

## BIM / CAD systémy

BIM a CAD nástroje jsou silné pro projektování, modely, výkresy, koordinaci a technickou dokumentaci. Pracují s vysokou přesností a jsou nezbytné pro mnoho větších stavebních procesů.

Kde končí: BIM/CAD není primárně nástroj pro rychlé zpracování běžné servisní fotodokumentace a tvorbu nabídky z terénních fotek. Vyžaduje jiný typ vstupů, vyšší odbornost a často slouží jiné fázi stavebního procesu.

**Srovnání**

NOVU Builder se nesnaží konkurovat modelovacím nástrojům. Je blíže operační vrstvě pro zakázky, které vznikají z reálného stavu v terénu a potřebují rychlý obchodní výstup.

## Přesné srovnání

**Srovnání**

- Obecná AI umí navrhnout odpověď. NOVU Builder má řídit stav.
- Stavební platformy umí široký projektový lifecycle. NOVU Builder cílí na užší photo-to-offer proces.
- Inspection apps umí dokumentovat závady. NOVU Builder chce navázat práci, cenu a nabídku.
- BIM/CAD umí projektovat a koordinovat modely. NOVU Builder řeší zakázku z fotek a provozního kontextu.

**Klíčový závěr**

Tržní prostor NOVU Builderu je mezi obecnou AI a velkými stavebními platformami. Produkt má smysl, pokud bude důsledně specializovaný, rychle nasaditelný a datově auditovatelný.

---

# 7. V čem se NOVU Builder zásadně liší

## Propojení AI -> akce -> rozpočet

Hlavní rozdíl je v návaznosti. AI nemá být doplněk na konci procesu, který pouze shrne data. AI má být zdroj návrhu, který se okamžitě promítne do akce: založení work itemu, vyplnění parametrů, upozornění na nejistotu, příprava podkladů pro pricing a následný export.

Toto propojení je technicky náročnější než jednoduchý chatbot, ale produktově mnohem hodnotnější. Pokud se podaří, uživatel nebude přepisovat AI odpověď do tabulky. Bude kontrolovat konkrétní datový návrh v systému.

## Jednotný workTypeCode model

**workTypeCode** je páteř produktu. Jednotný kód práce řeší problém, který by jinak vznikl mezi AI, UI, backendem a cenotvorbou. Bez něj by každá vrstva mohla používat jiný jazyk.

Příklad: AI detekuje opravu střechy. Katalog zná `roof-repair`. Tenant má pro tuto práci vlastní výchozí parametry a pricebook. Runtime vytvoří project work item. Pricing použije odpovídající profil. Export zobrazí obchodně čitelný výstup.

To je rozdíl mezi volným textem a systémovou akcí.

## Jedno source of truth

NOVU Builder se správně posouvá k modelu, kde je backend a databáze autoritativní. Klienti zobrazují a posílají akce. Redis slouží jako runtime transport a cache, ale nemá být jedinou pravdou o jobech, tokenech nebo auditu. Storage v produkci má být S3-compatible a databáze má držet storage keys.

Tento princip je zásadní pro škálování i bezpečnost. Bez jednoho source of truth se systém při růstu začne rozpadat: jiný stav v klientovi, jiný ve frontě, jiný v databázi a jiný v exportu.

## AI jako součást workflow

AI je v NOVU Builderu umístěna uvnitř workflow. To znamená, že její výstup má životní cyklus: vznikne v analysis jobu, uloží se, namapuje se, zobrazí se, člověk ho potvrdí nebo upraví a až potom se použije pro cenový nebo exportní výstup.

To je bezpečnější než nechat model přímo generovat finální nabídku. U stavebních zakázek je potřeba vědět, která hodnota je AI odhad, která je ruční korekce a která je finálně schválená hodnota.

**Shrnutí**

NOVU Builder se liší tím, že se nesnaží být nejchytřejší konverzací. Snaží se být nejlépe strukturovaným procesem pro konkrétní doménu.

---

# 8. Budoucí rozvoj

## Vlastní AI modely a fine-tuning

Dlouhodobě může být silnou cestou vlastní datová vrstva nad reálnými zakázkami. Fine-tuning nebo specializované modely dávají smysl až po získání dostatečně kvalitních dat: fotografie, potvrzené plochy, korekce, typy prací, materiály, ceny a výsledky.

Není vhodné začínat slibem vlastního modelu bez dat. Správný postup je nejprve sbírat strukturovanou zpětnou vazbu a měřit, kde AI dělá chyby. Teprve potom má smysl trénovat nebo dolaďovat modely pro konkrétní domény.

## Databáze materiálů a ceníků

Materiály a ceníky jsou přirozené rozšíření. Pokud má systém vytvářet nabídky, musí umět pracovat s interní cenovou politikou, dodavateli, cenovými profily, regionálními rozdíly a variantami.

Zde je důležité zachovat auditovatelnost. Cenový výstup musí být vysvětlitelný: jaké množství, jaká jednotka, jaký zdroj ceny, jaké pravidlo a jaká marže.

## Automatizace návrhů rekonstrukcí

Další produktová vrstva může být návrh rekonstrukčního scénáře. Nejen "opravit fasádu", ale navrhnout postup: příprava, očištění, penetrace, materiál, práce, kontrola, odhad délky a rizika.

Tato automatizace musí být modulární. Různé firmy budou mít různé postupy, ceny a preferované materiály. Proto má smysl kombinace globálního katalogu a tenant override vrstvy.

## Integrace s dodavateli

Integrace s dodavateli může zvýšit obchodní hodnotu. Produkt může časem napojit dostupnost materiálu, referenční ceny, objednávkový proces nebo doporučení dodavatele.

Riziko je, že příliš brzké integrace zpomalí vývoj jádra. Priorita by měla být nejprve spolehlivý workflow a pricing model, potom dodavatelské integrace.

## Prediktivní analýzy

Jakmile bude systém obsahovat dostatečné množství historických dat, vzniká prostor pro predikce: pravděpodobnost přijetí nabídky, typické korekce AI odhadu, čas do dokončení nabídky, rizikovost zakázky, odchylka mezi odhadem a skutečnou cenou.

To je investičně zajímavé, protože produkt se může posunout od evidence a návrhu k rozhodovací inteligenci. Podmínkou je kvalitní datová disciplína od začátku.

**Klíčové body**

- Nejprve sbírat kvalitní potvrzená data, potom trénovat modely.
- Ceníky a materiály musí být auditovatelné.
- Integrace mají přijít po stabilizaci jádra.
- Prediktivní analýzy jsou silná budoucí vrstva, ale závisí na datech.

---

# 9. Rizika

## Technická složitost

NOVU Builder není jednoduchá CRUD aplikace. Spojuje uploady, storage, AI, fronty, tenant izolaci, desktop klienta, exporty, cenovou logiku a audit. Každá vrstva má vlastní failure modes.

**Rizika**

- růst počtu edge casů,
- složitější testování,
- možnost driftu mezi dokumentací a implementací,
- riziko, že se business logika rozptýlí do klienta, backendu i AI promptů.

Mitigace spočívá v přísném vrstvení: route, service, repository, worker, AI provider a katalogové definice musí mít jasné hranice.

## Závislost na AI kvalitě

AI může špatně odhadnout plochu, zaměnit typ poškození nebo navrhnout nevhodný rozsah. U fotek navíc záleží na úhlu, světle, kvalitě, počtu snímků a kontextu.

Proto nesmí být AI výstup finální pravda. Musí mít confidence, validační upozornění a možnost ruční korekce. Produktová komunikace musí být přesná: AI asistuje, člověk potvrzuje, server přepočítá.

## Škálování backendu

Backend bude růstově zatížen třemi typy práce: běžné API requesty, těžké operace nad soubory a AI/worker úlohy. Pokud nebudou správně oddělené, těžké operace mohou poškodit běžnou odezvu.

**Rizika**

- exporty a image processing blokují API,
- AI provider latence drží worker sloty,
- fronty rostou rychleji než worker pool,
- DB pool se vyčerpá při burst provozu.

Mitigace: heavy lane, bounded queues, per-tenant caps, worker concurrency, DB pool monitoring a provider circuit breaker.

## Datová konzistence

Datová konzistence je zásadní. Pokud se rozjede stav mezi databází, storage, Redis frontou a klientem, systém ztratí důvěryhodnost.

Správný směr je používat databázi jako autoritativní pravdu pro business stav, storage keys místo veřejných URL, Redis jen jako runtime transport a auditní log pro citlivé operace.

## UX složitost

Produkt může být technicky silný, ale uživatel ho nepřijme, pokud workflow bude pomalé nebo nejasné. Kalkulant potřebuje rychle vidět: co přišlo, co navrhla AI, co chybí, co musí potvrdit a co lze odeslat.

UX riziko je zejména v tom, že systém zobrazí příliš mnoho technických detailů bez jasné priority. Desktop musí být pracovní nástroj, ne debug konzole.

**Shrnutí rizik**

Projekt má realistická rizika, ale většina z nich je mitigovatelná architekturou a provozní disciplínou. Největší nebezpečí by bylo prezentovat systém jako autonomní AI kalkulant místo jako kontrolované AI-assisted workflow.

---

# 10. Bezpečnost a stabilita

## Oddělení vrstev

Bezpečnost začíná architekturou. Klient nesmí být zdroj pravdy. AI nesmí být zdroj finální ceny. Redis nesmí být jediná business pravda. Produkční soubory nesmí být lokální dev storage.

Správné oddělení vrstev v NOVU Builderu je:

- klient: zobrazení, interakce, odeslání akce,
- backend: validace, autorizace, workflow, výpočet, audit,
- databáze: autoritativní stav,
- storage: autoritativní soubory,
- Redis: runtime transport, cache a fronty,
- worker: pomalé a asynchronní úlohy,
- AI provider: návrh strukturovaného výstupu.

## Fail-fast a fail-closed principy

Fail-fast znamená, že systém má špatnou konfiguraci odhalit hned, ne až při poškození dat. Fail-closed znamená, že při selhání kritické ochrany se operace nemá tvářit jako úspěšná.

Příklady:

- pokud produkce omylem padá na local storage, má se zastavit,
- pokud security-critical audit nejde zapsat, citlivá operace nemá tiše projít,
- pokud AI provider není implementovaný, má být blokovaný před runtime zpracováním,
- pokud processing plane není ready, readiness to musí ukázat.

## Auditovatelnost

Auditovatelnost je pro tento produkt zásadní. Zákazník musí mít možnost zjistit, kdo provedl změnu, kdy vznikl návrh, jaký byl zdroj hodnoty a co bylo finálně potvrzeno.

Audit není jen bezpečnostní log. Je to business vlastnost. U cenové nabídky může být důležité doložit, proč byla použita konkrétní plocha, materiál nebo varianta.

## Práce s daty klientů

Projekt pracuje s citlivými daty: fotografie objektů, adresy, interní ceníky, obchodní návrhy a uživatelské účty. Proto musí být tenant izolace součástí datového modelu, dotazů i testů.

Produkční storage má používat omezené signed URL a databáze má držet storage keys. Trvalé veřejné URL by zvyšovaly riziko úniku dat.

## API bezpečnost

API bezpečnost zahrnuje autentizaci, autorizaci, role, rate limiting, upload validaci, CORS politiku, request ID, logging redakci citlivých údajů a admin audit.

Důležité je také chránit systém proti abuse scénářům: bruteforce login, nadměrné uploady, nadměrné analysis jobs a cross-tenant přístup.

**Klíčové body**

- Backend je bezpečnostní hranice.
- Audit musí být DB-authoritative.
- Fail-fast je správný provozní princip.
- Storage musí být řízené přes keys a signed URL.
- Tenant izolace je nutná pro B2B důvěru.

---

# 11. Škálovatelnost a provoz

## Multi-tenant architektura

NOVU Builder je navržen jako multi-tenant systém. To znamená, že více firem používá stejnou platformu, ale jejich data, konfigurace a workflow musí být oddělené.

Silnou stránkou je tenant override model nad work catalogem. Globální katalog definuje základní typy prací a tenant ukládá pouze odchylky. To je důležité pro škálování. Pokud by každý tenant měl plnou kopii katalogu, systém by rychle ztratil udržovatelnost.

## Backend jako samostatná služba

Backend musí zůstat samostatnou službou s jasným API. To umožňuje napojit desktop, mobil, web nebo budoucí integrace bez přesunu business logiky do klientů.

Samostatný backend také umožňuje horizontální škálování. API instance mohou být stateless, zatímco stav zůstává v databázi, storage a frontách.

## Cloud vs lokální část

Kombinace desktopu a cloudu je pro produkt logická. Desktop může být lokální pracovní nástroj pro kancelář, ale data a rozhodování musí být centralizované.

Lokální část nesmí být autoritativní pro business data. Pokud by každá kancelář držela vlastní stav, škálování a audit by se výrazně zhoršily.

## Provozní model

Provozní model by měl rozlišovat tři roviny:

- **API plane** - běžné requesty, čtení a zápis dat.
- **Processing plane** - worker, AI jobs, exporty, image processing.
- **Safety plane** - audit, auth ochrana, storage readiness, metriky, alerty.

Toto rozdělení je důležité pro incident response. API může být částečně dostupné, i když processing běží degradovaně. Zákazník ale musí vidět pravdivý stav a systém nesmí přijímat úlohy, které nedokáže bezpečně zpracovat.

## Cesta k 100k+ klientům

100k+ klientů je realistický pouze jako postupný cíl. Vyžaduje:

- horizontální škálování API,
- worker pooly podle queue age a throughputu,
- oddělení Redis rolí pro auth, cache a queue,
- DB pooling, repliky a případně partitioning,
- tenant-aware quotas a noisy-neighbor ochranu,
- storage lifecycle pravidla,
- AI provider circuit breakers,
- dashboardy a alerty bez semantického driftu.

**Shrnutí**

Současná architektura má správné stavební prvky pro škálování, ale produkční růst musí být řízený. Nejprve pilot, potom load rehearsal, potom vyšší tenant concurrency a teprve poté agresivnější obchodní škálování.

---

# 12. Závěrečné hodnocení

## Silné stránky

NOVU Builder má silný směr, protože řeší konkrétní problém a nespoléhá pouze na obecnou AI schopnost. Projekt má jasné technické jádro: FastAPI backend, PostgreSQL, Redis, worker pipeline, Qt desktop, AI provider abstraction, work catalog a auditovatelné workflow.

Nejsilnější produktový prvek je **workTypeCode**. Tento model dává systému doménovou paměť a umožňuje spojit AI, cenu, workflow a export do jedné struktury.

Další silná stránka je realistický přístup k AI. Systém správně počítá s tím, že AI navrhuje a člověk potvrzuje. To je vhodnější pro stavebnictví než slib plné autonomie.

## Slabiny

Projekt je technicky komplexní a bude vyžadovat disciplínu. Slabá místa jsou zejména:

- load profil těžkých operací,
- oddělení Redis failure domains,
- dotažení monitoring a alerting kontraktu,
- UX jednoduchost v desktopu,
- kvalita AI výstupu na reálných fotkách,
- důsledné udržení business logiky na backendu.

Tyto slabiny nejsou důvodem k zastavení. Jsou to konkrétní oblasti pro hardening před širším provozem.

## Potenciál

Potenciál projektu je vysoký, pokud bude veden jako specializovaný B2B produkt, ne jako obecná AI aplikace. Nejlepší tržní pozice je: systém pro firmy, které pravidelně tvoří nabídky ze stavební fotodokumentace a potřebují rychlost, konzistenci a kontrolu.

Investor by měl vnímat NOVU Builder jako produkt s jasnou vertikální specializací. Zákazník by ho měl vnímat jako nástroj, který zkracuje cestu od fotky k nabídce a zároveň zachovává kontrolu nad cenou a odpovědností.

## Finální verdikt

NOVU Builder je technicky obhajitelný základ pro řízený pilot a další produktový hardening. Není korektní prezentovat ho jako hotový enterprise systém pro masové nasazení bez dalších kroků. Je korektní prezentovat ho jako promyšlenou platformu, která má jasné doménové jádro, reálný obchodní problém, auditovatelný workflow a realistickou cestu ke škálování.

**Závěr**

NOVU Builder má největší hodnotu tam, kde se obecná AI mění v konkrétní akci: typ práce, parametr, cena, dokument a rozhodnutí. Pokud si projekt udrží technickou disciplínu a úzké produktové zaměření, může se stát silným specializovaným nástrojem pro stavební a servisní firmy.

