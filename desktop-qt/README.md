# Desktop Qt

Tato slozka je novy cilovy desktop klient pro kancelarskou cast FotoNabidky.

Aktualni stav:

- funkcni Qt6 desktop prototyp
- Qt6 Widgets smer
- architektura `views + viewmodels + services + dto`
- realne API napojeni na Python backend pro hlavni desktop workflow

Desktop dnes umi:

- nacist seznam `cases`
- nacist detail `case`
- nacist `images` pro zakazku
- vytvorit kopii zakazky (`duplicate`)
- ulozit `proposal draft`
- vytvorit `final proposal`
- odeslat zakazku (`send`)
- nastavit hlavni fotku
- nastavit referencni fotku pro analyzu
- nahrat fotky na backend

Prvni obrazovky, ktere budeme postupne dodelavat:

- Login
- Dashboard
- Case list
- Case detail
- Photos tab
- Findings tab
- Overlay viewer

Poznamka k aktualnimu stavu:

- login view zatim slouzi hlavne jako vstup do desktop workflow
- hlavni pracovni cast uz bezi nad backend API na `http://127.0.0.1:8000/api/v1`
- cast navigace a nektere sekce jsou zatim jen pripraveny stub pro dalsi kroky

React v `novu-react/` zustava jen jako referencni prototyp workflow a UI logiky.

## Build

Pro lokalni Windows build pouzij:

```bat
scripts\build-debug.cmd
```

Skript nejdriv nacte `VsDevCmd.bat` pro MSVC prostredi a potom spusti `cmake --build`
nad aktualnim Qt Creator build adresarem `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug`.

Robustnejsi varianta s logem a stavem buildu:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-debug.ps1
```

Skript zapise:

- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\build-debug-status.json`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\build-debug-last.txt`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\build-debug-*.stdout.log`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\build-debug-*.stderr.log`

Status je vzdy jeden z:

- `success`
- `failed`
- `timeout`

## Setup na novem PC

Pred prvnim buildem na novem Windows PC si over:

- nainstalovane `Qt 6.x`
- `Qt Creator`
- `Visual Studio 2022` nebo `Build Tools` s `MSVC`
- dostupny `cmake`

Doporuceny postup:

1. otevri `desktop-qt/CMakeLists.txt` v `Qt Creatoru`
2. nech Qt Creator vytvorit nebo potvrdit build kit pro `Qt 6 + MSVC2022 64bit`
3. nech vytvorit build adresar `build/Desktop_Qt_6_10_2_MSVC2022_64bit-Debug`
4. pak spust:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-debug.ps1
```

Pokud backend bezi na `http://127.0.0.1:8000`, muzes hned potom pustit:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1
```

## Smoke Check

Pro rychle overeni desktop + backend workflow pouzij:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-check.ps1
```

Smoke check overi:

- backend health endpoint `http://127.0.0.1:8000/api/v1/health`
- existenci `FotoNabidkaDesktop.exe`
- posledni build status z `automation-logs`

Vysledek uklada do:

- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-check-status.json`

## Smoke Workflow

Pro skutecne overeni hlavniho toku `reference case -> images -> Save As duplicate -> cleanup` pouzij:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-workflow.ps1
```

Skript:

- overi backend health
- najde prvni `[TEST]` / `ref_case_*` zakazku s fotkami
- overi, ze zdrojovy case ma images
- pres API zavola `Save As` (`POST /api/v1/cases/{id}/duplicate`)
- zkontroluje, ze nova kopie ma:
  - spravny nazev `... - Kopie`
  - stejny pocet fotek
  - hlavni fotku
  - referencni fotku pro analyzu
- po testu novou `prj_*` kopii smaze, aby nezustal bordel v datech

Vysledek uklada do:

- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-workflow-status.json`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-workflow-last.txt`

## Smoke Final Proposal

Pro druhy hlavni tok `duplicate -> final proposal -> auto DOCX/PDF -> cleanup` pouzij:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-final-proposal.ps1
```

Skript:

- overi backend health a startup readiness
- vytvori dev kopii reference case
- zavola `POST /api/v1/cases/{id}/final-proposal`
- overi, ze vznikla finalni verze
- overi, ze v `storage\exports\{case_id}` vznikl aspon jeden `.docx` a `.pdf`
- po testu kopii zase smaze

Vysledek uklada do:

- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-final-proposal-status.json`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-final-proposal-last.txt`

## Startup Kontroly

Backend pri startu ted fail-fast overuje:

- database connectivity
- pristup ke schema tabulkam
- zapis do `storage`

Desktop pri startu provede kratkou kontrolu `http://127.0.0.1:8000/api/v1/health` a kdyz backend neni pripraveny, ukaze varovani hned pri spusteni.

## Smoke Draft / Send Guard

Pro workflow `proposal draft patch -> final proposal -> send guard` pouzij:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-draft-send-guard.ps1
```

Skript overi:

- ze `send` pred final proposal vraci `409`
- ze patch do `proposal draft` se propise
- ze `final proposal` prevezme upraveny draft
- ze `send` po final proposal projde
- a po testu kopii zase smaze

Vysledek uklada do:

- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-draft-send-guard-status.json`
- `build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug\automation-logs\smoke-draft-send-guard-last.txt`
