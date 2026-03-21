# Runtime Responsibilities

Tento dokument rika jednoduse a prakticky:

- co ma delat mobilni klient
- co ma delat desktop klient
- co ma delat server API
- co ma delat AI vrstva
- co patri do dalsi implementace

Cil:

- neztratit se v dalsim vyvoji
- nepresouvat logiku na spatnou vrstvu
- vedet, co ma byt priorita pred beta verzi

## 1. Zakladni pravidlo

Rozdeleni odpovednosti produktu:

- `mobilni klient` = sber dat v terenu
- `desktop klient` = pracovni rozhrani pro cloveka
- `server API` = zdroj pravdy, business logika a orchestrator
- `AI worker` = analyza obrazu a navrh strukturovanych vystupu

Jednoducha veta:

`Mobil sbera. Desktop kontroluje. Server rozhoduje a uklada. AI navrhuje.`

## 2. Co ma delat mobilni klient

Mobilni aplikace ma byt vychozi vstup v terenu.

Mobil ma resit:

- zalozeni nebo otevreni zakazky
- porizeni fotek
- odeslani fotek a zakladnich metadat na server
- zobrazeni stavu uploadu a zakladniho workflow

Mobil nema delat:

- vypocet ceny
- rozhodovani o finalni plose
- navrh finalni nabidky
- praci s ceniky, dodavateli a firmami

Pravidlo:

- mobil jen odesila vstup
- backend zpracuje zbytek workflow

## 3. Co ma delat desktop klient

Desktop aplikace nema byt mozek systemu.
Je to ovladaci a kontrolni vrstva pro kalkulanta nebo managera.

Desktop ma resit:

- prihlaseni uzivatele
- seznam projektu
- detail projektu
- zobrazeni fotek
- zobrazeni workflow stavu a blokaci
- kontrolu serveroveho navrhu
- rucni korekci plochy nebo textu
- upravu cisel a textu pred schvalenim
- schvaleni finalni nabidky a odeslani

Desktop nema delat:

- finalni vypocet ceny
- finalni AI analyzu
- vyber dodavatelu a firem mimo serverova pravidla
- rozhodovani o tom, ktera data jsou autoritativni
- praci s primarnim ulozistem souboru

Pravidlo:

- klient muze odeslat zmenu
- server ji overi, ulozi a vrati vysledek

## 4. Co ma delat server API

Server je centralni vrstva produktu.
Je to misto, kde musi byt:

- databaze
- business logika
- integrace
- audit
- fronty

Server ma resit:

- autentizaci a role
- CRUD projektu
- spravu fotek a jejich metadat
- workflow stav zakazky od uploadu po schvaleni
- validaci vstupu
- spravu analyz
- spravu firemniho ceniku
- spravu dodavatelu
- vypocet cenovych variant
- navrh praci a materialu
- vyber firem a dodavatelu podle pravidel
- navrh finalni nabidky
- rozhodovani, jestli se ma pouzit AI plocha nebo manualni plocha
- generovani dokumentu
- emailing
- audit log a historii zmen

Server je autorita pro:

- projekty
- fotografie a jejich metadata
- analysis results
- proposal draft
- final proposal
- quote variants
- quote items
- firemni ceny
- dodavatelske zdroje

Server nema delat:

- tezke obrazove vypocty primo v request handleru
- slozite synchronni AI volani, ktera blokuji UI

Pravidlo:

- tezka nebo pomala prace ma jit do jobu nebo AI workeru

## 5. Co ma delat AI worker

AI worker neni backend cele aplikace.
Je to specializovana vrstva na analyzu fotek a pripravu navrhu.

AI worker ma resit:

- klasifikaci objektu z fotky
- posouzeni stavu povrchu
- navrh rozsahu opravy
- segmentaci nebo masku oblasti opravy
- odhad plochy
- navrh materialu
- navrh workflow
- confidence score

AI worker ma vratit strukturovany vystup, ne finalni obchodni rozhodnuti.

AI worker nema mit posledni slovo nad:

- finalni plochou
- finalni cenou
- finalni podobou nabidky

Pravidlo:

- AI navrhne
- clovek potvrdi
- server prepocita

## 6. Co bude zpracovavat server v beta verzi

Pro beta verzi by mel server umet tyto bloky:

### 6.1 Projekty

- zalozit projekt
- upravit projekt
- vratit seznam projektu
- vratit detail projektu

### 6.2 Fotky

- prijmout metadata fotek
- pozdeji prijmout i fyzicke soubory
- ulozit vychozi fotku
- vratit seznam fotek k projektu

### 6.3 AI orchestraci

- po uploadu fotek spustit analyze job
- predat vstup do AI provideru
- ulozit analysis result
- vratit posledni analyze

### 6.4 Pricing engine

- nacist posledni analyze
- rozhodnout, jaka plocha je finalni
- vzit firemni ceny a normy
- prepocitat economy / standard / premium variantu
- ulozit quote items
- pripravit proposal draft a final proposal

### 6.5 Dodavatele a materialy

- vratit firemni katalog
- vratit dodavatele
- vratit referencni ceny
- ulozit firemni cenu
- ulozit zdroj dodavatele

### 6.6 Dokumenty

Tohle jeste neni hotove, ale do beta verze patri:

- generovani PDF
- pozdeji DOCX
- ulozeni dokumentu k projektu

### 6.7 Komunikace

Tohle jeste neni hotove, ale do beta verze patri:

- odeslani nabidky emailem
- log o odeslani

## 7. Co bude klient delat v beta verzi

Desktop klient ma byt pripravny na tento realny tok:

1. otevrit projekt, ktery prisel z mobilu
2. zkontrolovat fotky a workflow stav
3. zkontrolovat AI plochu
4. pripadne zakreslit oblast nebo zadat manualni m2
5. zkontrolovat serverovy navrh praci, materialu a ceny
6. upravit text nebo cisla
7. potvrdit finalni verzi
8. odeslat nabidku

## 8. Kde ma byt jaka logika

Prakticky tahak:

### V mobilu

- upload fotek
- zakladni metadata
- zobrazeni stavu odeslani

### V desktop klientovi

- formularove stavy
- vyber aktivniho projektu
- vyber aktivni fotky
- lokalni polygon body pred ulozenim
- zobrazeni uspechu a chyb

### Na serveru

- validace payloadu
- finalni update databaze
- workflow blokace a povolene akce
- rozhodovani o area source
- navrh praci
- navrh materialu
- vyber firem a dodavatelu
- vypocet variant
- mapovani materialu
- sprava jobu
- integrace se storage
- dokumenty
- e-mail

### V AI workeru

- computer vision
- model prompt / inference
- normalizovany AI vystup

## 9. Co nedelat spatne

Tady jsou nejcastejsi architektonicke chyby, kterym se chceme vyhnout:

- nepocitat finalni cenu jen na klientovi
- nedavat AI posledni slovo nad cenou
- nenechat klient rozhodovat o autoritativnich datech bez serverove validace
- nedavat business logiku do mobilu
- nemichat dokumenty, AI a pricing do jednoho obriho route handleru
- nenechavat tezke AI volani blokovat bezny request, pokud to nebude nutne

## 10. Dalsi doporucene serverove moduly

Jakmile dokoncime desktop polish, dalsi logicke serverove bloky jsou:

1. `photo upload/storage`
- realny upload souboru
- local/dev storage nejdriv, S3-compatible pozdeji
- pripravit tri varianty kazde fotky:
  - `original`
  - `preview`
  - `ai_input`

2. `document service`
- generovani PDF
- priprava na DOCX

3. `email service`
- odeslani klientovi
- archivace odeslani

4. `auth`
- realne prihlaseni
- role admin / manager / field worker

5. `async jobs`
- priprava na fronty pro AI a dokumenty

## 11. Doporucene poradi dalsi prace

Prakticky doporuceny sled:

1. dokoncit backend workflow stav a blokace
2. zaviest realny mobile-first photo upload
3. pripravit serverove uloziste souboru
4. napojit prvni realny AI provider
5. pripravit proposal draft a final proposal pipeline
6. pridat PDF a DOCX generator
7. pridat email odeslani
8. doresit auth a role

Toto poradi dava nejvetsi smysl pro soukromou beta verzi.
