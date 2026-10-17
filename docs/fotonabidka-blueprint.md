# FotoNabidka

Finalni technicky blueprint pro MVP a dalsi rust produktu.

## 1. Cilem produktu

Produkt ma zjednodusit tvorbu stavebnich cenovych nabidek tak, aby:

- technik v terenu jen vyfotil objekt, pridal kratkou poznamku a odeslal data
- server provedl AI analyzu a pripravil navrh nabidky
- pracovnik v kancelari nabidku zkontroloval, upravil a odeslal klientovi

Hlavni hodnota produktu:

`vyfotit -> analyzovat -> upravit -> odeslat`

## 2. Hlavni architektonicke rozhodnuti

Pro prvni verzi nebudeme stavet tezky system s mnoha mikrosluzbami ani nativni desktop aplikaci.

Zvoleny smer:

- mobilni aplikace pro teren
- webova aplikace na PC pro kancelar
- centralni backend s business logikou
- samostatny AI worker pro obrazovou analyzu

To znamena:

- ano pro kombinaci vice technologii
- ne pro zbytecnou slozitost hned na zacatku

## 3. Doporuceny stack

### 3.1 Mobil

- React Native
- Expo
- TypeScript

Proc:

- rychly vyvoj pro iOS i Android z jednoho kodu
- snadna prace s kamerou, lokalnim ulozistem a GPS
- vhodne pro jednoduche a rychle workflow v terenu

Mobil bude resit jen:

- prihlaseni
- novy projekt
- foto
- GPS
- kratky popis
- odeslani na server
- zobrazeni zakladniho nahledu vysledku

### 3.2 Kancelarska aplikace

- React
- TypeScript
- Vite v zacatku
- pozdeji muzeme prejit na Next.js, pokud bude davat smysl

Proc:

- rychle UI
- dobre sdileni znalosti v tymu
- snadne rozsireni o tabulky, editory a dokumentove workflow

Kancelarska cast bude resit:

- seznam projektu
- detail projektu
- kontrolu AI vystupu
- upravu plochy
- upravu materialu, cen a marzi
- generovani nabidky
- odeslani emailu

### 3.3 Backend API

- Node.js
- TypeScript
- Fastify nebo NestJS

Proc:

- dobra produktivita
- sdilene typy s frontendem
- vhodne pro business logiku, CRUD, auth, integrace a API

Backend bude resit:

- autentizaci a role
- projekty a zakazky
- upload fotek
- metadata projektu
- pricing engine
- generovani dokumentu
- emailing
- audit log

### 3.4 AI worker

- Python
- FastAPI
- OpenCV
- segmentacni model

Proc:

- obrazove zpracovani a CV knihovny jsou zde prirozenejsi nez v Node.js
- lze oddelit vypocetne narocne AI ulohy od hlavniho API

AI worker bude resit:

- predzpracovani fotografii
- segmentaci oblasti oprav
- odhad plochy
- pripravu strukturovaneho AI vysledku pro backend

### 3.5 Data a infrastruktura

- PostgreSQL pro primarni data
- Redis pro fronty a background joby
- S3 kompatibilni object storage pro fotky a dokumenty

## 4. Vrstvy systemu

## 4.1 Mobilni vrstva

Vstup od technika:

- fotografie
- GPS souradnice
- kratky popis zavady nebo poptavky
- volitelne kontakt na klienta

Mobil nema pocitat cenu ani delat AI analyzu.

## 4.2 Serverova vrstva

Server je mozek systemu.

Prijme:

- fotografie
- GPS
- metadata projektu

Vrati:

- adresu z geocodingu
- odhad typu objektu
- navrzeny rozsah zasahu
- odhad plochy
- tri varianty nabidky
- navrh materialu a postupu

## 4.3 Kancelarska vrstva

Kancelarske rozhrani je misto, kde se dela kontrola a finalni rozhodnuti.

Uzivatel zde:

- vidi projekt a vysledky AI
- upravi polygon nebo plochu
- upravi ceny a materialy
- schvali finalni variantu
- vygeneruje PDF a DOCX
- odesle klientovi nabidku

## 5. Doporuceny workflow

1. Technik zalozi novy projekt v mobilu.
2. Vyfoti objekt nebo jeho cast.
3. Mobil prilozi GPS a kratky popis.
4. Data se odeslou na server.
5. Backend vytvori projekt a zaradi AI ulohu do fronty.
6. AI worker zpracuje obraz, vrati klasifikaci, masku oblasti a odhad plochy.
7. Backend dopocita cenove varianty podle firemnich nastaveni.
8. Kancelarsky uzivatel otevre projekt ve webu.
9. Upravi detaily a vygeneruje nabidku.
10. Nabidka se ulozi a odesle klientovi.

## 6. AI pipeline

AI pipeline by mela byt rozdelena na dve casti.

### 6.1 Vision a strukturovany vystup

Pouziti:

- rozpoznani typu objektu
- odhad stavu povrchu
- navrh typu zasahu
- navrh pracovnich kroku a materialu

Doporuceni:

- pouzit vision model s podporou strukturovaneho vystupu
- vzdy vracet confidence
- nevkladat AI vystup rovnou do finalni ceny bez business logiky

### 6.2 Segmentace a plocha

Pouziti:

- nalezeni oblasti opravovane casti na fotografii
- priprava polygonu pro editaci

Doporuceni:

- segmentacni CV model v Python workeru
- OpenCV pro doplnkove zpracovani
- finalni plocha musi jit rucne opravit

## 7. Jak pocitat plochu z fotografie

Plocha z jedne fotky bez meritka nebude nikdy dokonale spolehliva.

Proto bude system pracovat hybridne:

1. AI navrhne oblast.
2. System odhadne meritko.
3. Uzivatel muze oblast upravit.
4. System vzdy ulozi confidence.

Mozne zdroje meritka:

- znamy objekt na fotce
- referencni rozmer zadany uzivatelem
- vice fotek jednoho objektu
- pozdeji lidar nebo AR, pokud to zariovani umozni

Pravidlo produktu:

- AI pomaha
- clovek potvrzuje

## 8. Cenovy engine

Ceny nema urcovat jen AI.

AI muze navrhnout:

- druh zasahu
- materialy
- mnozstvi na m2
- normu prace
- text do nabidky

Finalni cena musi byt vypoctena deterministicky:

- plocha
- norma prace
- hodinova sazba
- material
- doprava
- leasing nebo leseni
- odpad
- marze
- DPH

Vystupem budou tri varianty:

- ekonomicka
- standardni
- premium

## 9. Datovy model MVP

Minimalni entity pro prvni verzi:

- `organizations`
- `users`
- `clients`
- `projects`
- `project_photos`
- `project_addresses`
- `analysis_jobs`
- `analysis_results`
- `pricing_profiles`
- `quote_variants`
- `quote_items`
- `documents`
- `email_logs`
- `audit_logs`

## 10. Co patri do MVP

Do MVP patri:

- prihlaseni
- zalozeni projektu
- nahrani fotek
- GPS a adresa
- AI analyza zakladniho typu zasahu
- zakladni odhad plochy
- tri cenove varianty
- kancelarska editace
- export PDF

Do pozdejsi faze patri:

- DOCX se slozitymi sablonami
- pokrocile dashboardy
- scraping cen stavebnin
- plne offline kancelarske rozhrani
- nativni desktop instalace
- pokrocily multi-photo measurement engine

## 11. Co nebudeme delat hned

Nebudeme na zacatku stavet:

- mikrosluzby pro kazdou drobnost
- nativni desktop app
- slozity sync engine mezi desktopem a cloudem
- ERP funkce
- fakturaci
- BIM

## 12. Doporucena struktura repozitare do dalsi faze

Postupne smerovat k teto strukture:

```text
apps/
  web/
  mobile/
  api/
services/
  ai-worker/
packages/
  shared-types/
  pricing-engine/
docs/
```

Nemusime to preskladat hned dnes, ale tohle je cilovy tvar.

## 13. Roadmapa

### Faze 1

- sjednotit repo
- opravit spousteni
- navrhnout schema databaze
- vytvorit API kontrakty

### Faze 2

- projekt CRUD
- upload fotek
- seznam projektu v kancelarskem rozhrani

### Faze 3

- AI pipeline v zakladni verzi
- preview vysledku
- pricing engine

### Faze 4

- editace plochy
- PDF export
- odesilani nabidek

## 14. Rozhodnuti pro tuto chvili

Aktualni doporuceni:

- React zustava pro kancelarskou cast
- mobil bude samostatna app
- backend bude centralni a typovy
- Python bude pouzit pro AI a obrazovou analyzu
- nativni desktop odkladame

To je nejlepsi pomer mezi kvalitou architektury, rychlosti vyvoje a obchodni realitou produktu.
