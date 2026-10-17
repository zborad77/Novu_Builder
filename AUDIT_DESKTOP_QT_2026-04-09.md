# Desktop-Qt Audit — 2026-04-09

**Autor:** Claude (senior Qt architekt review)
**Stav:** Krok 1 implementován, kroky 2–10 naplánované

---

## A) Audit současného stavu

### Desktop-qt — co tam je

**Struktura souborů:**
```
desktop-qt/
├── CMakeLists.txt
└── src/
    ├── main.cpp
    ├── mainwindow.h/.cpp
    ├── dto/                   ← 12 header-only struct souborů
    │   ├── adminjobdto.h
    │   ├── adminuserdto.h
    │   ├── auditlogdto.h
    │   ├── casedto.h
    │   ├── companydto.h
    │   ├── exportdto.h
    │   ├── imagedto.h
    │   ├── impersonatedto.h
    │   ├── logindto.h
    │   ├── loginresultdto.h
    │   ├── proposaldraftpatchdto.h
    │   └── uploadimagedto.h
    ├── services/
    │   ├── apiservice.h/.cpp  ← monolitický, všechna volání API
    │   └── sessionservice.h/.cpp
    ├── viewmodels/
    │   ├── loginviewmodel.h/.cpp
    │   ├── dashboardviewmodel.h/.cpp
    │   ├── caselistviewmodel.h/.cpp
    │   └── casedetailviewmodel.h/.cpp
    ├── views/
    │   ├── loginview.h/.cpp
    │   ├── dashboardview.h/.cpp
    │   ├── caselistview.h/.cpp
    │   ├── casedetailview.h/.cpp
    │   ├── casebrowserview.h/.cpp
    │   ├── newcaseview.h/.cpp
    │   ├── adminpanelview.h/.cpp
    │   └── serversetupdialog.h/.cpp
    └── widgets/
        └── imageoverlaywidget.h/.cpp
```

### Cílová architektura (dle `docs/08_frontend_directory_structure.md`)

| Cíl | Současnost |
|-----|------------|
| `src/network/` + split APIs | `src/services/apiservice.h` (monolit) |
| `src/models/` | `src/dto/` |
| `src/ui/` s podsložkami (auth/, cases/, widgets/) | `src/views/` + `src/widgets/` |
| `src/state/` | `src/services/sessionservice.h` |
| `src/app/`, `src/core/`, `src/utils/` | neexistuje |

### Backend API kontrakty — stav alignmentu

| Endpoint | Desktop volání | Stav |
|----------|---------------|------|
| `GET /cases` | `fetchCases()` → parsuje `ProjectListResponse.items` | ✓ správně |
| `POST /cases` | `createCase()` → posílá `source:"desktop"` + title/address/scope | ✓ správně |
| `GET /cases/{id}` | `fetchCaseDetail()` → parsuje `ProjectDetail` | ✓ správně |
| `POST /cases/{id}/duplicate` | `duplicateCase()` | ✓ správně |
| `PATCH /cases/{id}/proposal-draft` | `updateCaseProposalDraft()` | ✓ správně |
| `POST /cases/{id}/final-proposal` | `createCaseFinalProposal()` | ✓ správně |
| `POST /cases/{id}/send` | `sendCase()` | ✓ správně |
| `GET /cases/{id}/images` | `fetchCaseImages()` | ✓ správně |
| `POST /cases/{id}/analysis-jobs` | `triggerAnalysisJob()` | ✓ správně |
| `GET /analysis-jobs/{id}` | `getAnalysisJobStatus()` | ✓ správně |
| `PATCH /cases/{id}/analysis-results/{id}/selection` | `patchAnalysisSelection()` | ✓ správně |
| `POST /cases/{id}/exports/{type}` → `GET /exports/{id}` | `triggerExport()` | ✓ správně |
| `GET /cases?cursor=...` (paginace) | **ignorováno** | ✗ gap |
| `PATCH /cases/{id}` (general patch) | **neimplementováno** | ✗ gap |
| `POST /cases/{id}/exports/case-zip` | exportAsZip() dělá lokální ZIP vlastnoručně | ~ obchází |

---

## B) Přesný seznam potřebných změn

### Skupina 1 — Naming (DOKONČENO v kroku 1)

| # | Soubor | Problém | Úprava | Stav |
|---|--------|---------|--------|------|
| 1.1 | `CMakeLists.txt` | Projekt `FotoNabidkaDesktop` (4× v souboru) | → `NovuBuilder` | ✅ hotovo |
| 1.2 | `src/main.cpp:8` | `"FotoNabidka Desktop"` | → `"NOVU Builder"` | ✅ hotovo |
| 1.3 | `src/mainwindow.cpp:30` | `"FotoNabidka Desktop"` | → `"NOVU Builder"` | ✅ hotovo |
| 1.4 | `src/mainwindow.cpp:33,938` | `QSettings("NOVU","FotoNabidkaDesktop")` | → `QSettings("NOVU","NovuBuilder")` | ✅ hotovo |
| 1.5 | `src/services/sessionservice.cpp:30,37,44` | `QSettings("NovuHub","FotoNabidka")` | → `QSettings("NOVU","NovuBuilder")` (sjednocení namespace) | ✅ hotovo |
| 1.6 | `src/views/casedetailview.cpp:2531` | temp dir `"/FotoNabidka"` | → `"/NovuBuilder"` | ✅ hotovo |
| 1.7 | `src/views/casedetailview.cpp:2579` | temp dir `"/FotoNabidka/export_"` | → `"/NovuBuilder/export_"` | ✅ hotovo |
| 1.8 | `CMakeLists.txt` | Chybí aktivní DTO headers v source listu | Přidáno: `auditlogdto.h`, `companydto.h`, `exportdto.h`, `impersonatedto.h`, `loginresultdto.h`, `proposaldraftpatchdto.h` | ✅ hotovo |

### Skupina 2 — Přejmenování src/dto/ → src/models/

| # | Soubor/složka | Problém | Navržená úprava | Riziko |
|---|--------------|---------|----------------|--------|
| 2.1 | `src/dto/` (adresář) | Nesoulad s cílovou architekturou | Přejmenovat na `src/models/` | Nízké |
| 2.2 | Všechny `#include "dto/..."` (~25 výskytů) | Rozbité include cesty po přejmenování | Batch replace `"dto/` → `"models/` | Nízké |
| 2.3 | `CMakeLists.txt` — cesty k DTO | Rozbité cesty po přejmenování | Update `src/dto/...` → `src/models/...` | Nízké |

Postižené soubory pro include update:
- `src/services/apiservice.h` (imports casedto, imagedto, loginresultdto, exportdto, adminjobdto, adminuserdto, auditlogdto, companydto, impersonatedto, proposaldraftpatchdto, uploadimagedto)
- `src/viewmodels/loginviewmodel.h` (logindto)
- `src/viewmodels/caselistviewmodel.h` (casedto)
- `src/views/casebrowserview.h` (casedto)
- `src/views/caselistview.h` (casedto)
- `src/views/casedetailview.h` (casedto, imagedto, uploadimagedto)
- `src/views/newcaseview.h` (uploadimagedto)

### Skupina 3 — Přejmenování src/views/ → src/ui/

| # | Co | Úprava |
|---|-----|--------|
| 3.1 | `src/views/loginview.*` | → `src/ui/auth/loginview.*` |
| 3.2 | `src/views/serversetupdialog.*` | → `src/ui/auth/serversetupdialog.*` |
| 3.3 | `src/views/caselistview.*`, `casebrowserview.*`, `casedetailview.*`, `newcaseview.*` | → `src/ui/cases/` |
| 3.4 | `src/views/dashboardview.*` | → `src/ui/dashboard/` |
| 3.5 | `src/views/adminpanelview.*` | → `src/ui/admin/` |
| 3.6 | `src/widgets/imageoverlaywidget.*` | → `src/ui/widgets/` |

### Skupina 4 — SessionService přesun do src/state/

| # | Co | Úprava |
|---|-----|--------|
| 4.1 | `src/services/sessionservice.h/.cpp` | → `src/state/sessionstate.h/.cpp` (přejmenování třídy SessionService → SessionState) |
| 4.2 | Všechny `#include "services/sessionservice.h"` | → `#include "state/sessionstate.h"` |

### Skupina 5–7 — Rozpad ApiService do src/network/

| # | Nová třída | Extrahované metody | Krok |
|---|-----------|-------------------|------|
| 5 | `AuthApi` | `login()` | 5 |
| 6 | `CasesApi` | `fetchCases()`, `createCase()`, `duplicateCase()`, `fetchCaseDetail()`, `sendCase()`, `updateCaseProposalDraft()`, `createCaseFinalProposal()` | 6 |
| 7 | `ImagesApi` | `fetchCaseImages()`, `moveCaseImage()`, `setCasePrimaryImage()`, `setCaseAnalysisReferenceImage()`, `uploadCaseImages()`, `fetchImageData()` | 7a |
| 7 | `AnalysisApi` | `triggerAnalysisJob()`, `getAnalysisJobStatus()`, `patchAnalysisSelection()` | 7b |
| 7 | `ExportsApi` | `triggerExport()`, `downloadExportFile()` | 7c |

Společný základ: extrahovat helper `waitForReply()` a `makeAuthRequest()` do `src/network/ApiClient.h/.cpp`.

### Skupina 8 — Paginace

| # | Co | Úprava | Priorita |
|---|-----|--------|---------|
| 8.1 | `fetchCases()` — ignoruje `next_cursor` | Přidat čtení `next_cursor`, opakovat GET pokud není null | Střední |
| 8.2 | `CaseBrowserView` — neví o stránkování | Přijímat kompletní seznam (po dofetchování) | Střední |

### Skupina 9 — src/core/Config

| # | Co | Úprava |
|---|-----|--------|
| 9.1 | Hardcoded app name, org name, QSettings keys | Centralizovat do `src/core/Config.h` jako `constexpr` konstanty |

### Skupina 10 — Cleanup

| # | Co | Problém | Úprava |
|---|-----|---------|--------|
| 10.1 | `src/dto/logindto.h` + `LoginViewModel` | `LoginDto {email, password}` je triviální wrapper, `LoginViewModel` dělá jen validaci prázdnosti | Zvážit odstranění; login flow je přímočarý |

---

## C) Migrační plán

```
Krok 1  [✅ HOTOVO]   Naming — FotoNabidkaDesktop → NovuBuilder (main.cpp, CMakeLists,
                       mainwindow, sessionservice, temp cesty) + sync CMakeLists headers

Krok 2  [⬜ PŘÍŠTĚ]   Přejmenovat src/dto/ → src/models/
                       + Update všech #include "dto/..." → "models/..."
                       + Update CMakeLists.txt

Krok 3  [⬜]          Přejmenovat src/views/ → src/ui/ s podsložkami
                       (auth/, cases/, dashboard/, admin/, widgets/)
                       + Update #include + CMakeLists

Krok 4  [⬜]          SessionService → src/state/SessionState
                       (přejmenování třídy + přesun souboru + update includes)

Krok 5  [⬜]          Extrahovat AuthApi + ApiClient z ApiService
                       (login, makeAuthRequest, waitForReply, token management)

Krok 6  [⬜]          Extrahovat CasesApi z ApiService

Krok 7  [⬜]          Extrahovat ImagesApi + AnalysisApi + ExportsApi z ApiService
                       → ApiService se stane prázdný, lze odstranit

Krok 8  [⬜]          Paginace — čtení next_cursor z fetchCases

Krok 9  [⬜]          src/core/Config.h — centrální konstanty
                       (APP_NAME, ORG_NAME, QSETTINGS_KEY, APP_VERSION)

Krok 10 [⬜]          Cleanup — logindto + LoginViewModel (zvážit odstranění)
```

---

## F) Rizika a otevřené body

### Reálné

**QSettings migration (krok 1 vedlejší efekt):**
- Server URL byla pod `("NOVU","FotoNabidkaDesktop")`, tokeny pod `("NovuHub","FotoNabidka")`.
- Po rename: oba klíče nečitelné → dialog pro zadání serveru + nové přihlášení.
- V pilotní fázi přijatelné. Pro produkční upgrade: přidat jednorázový migration kód v `MainWindow::MainWindow()`.

**Binárka se přejmenuje na `NovuBuilder.exe`:**
- Qt Creator build konfigurace (`.qtc/CMakeLists.txt.user`) je nutné regenerovat přes "Run CMake".
- Stávající shortcuty/bat skripty odkazující na `FotoNabidkaDesktop.exe` přestanou fungovat.

**Paginace (skupina 8):**
- `GET /cases` vrací `next_cursor`. Při >200 zakázkách se část ztratí bez chyby.
- Dnes: pilotní fáze, nízký počet zakázek. Stane se bugem při škálování.

**Lokalní ZIP vs. backend case-zip:**
- `exportAsZip()` v `casedetailview.cpp` vytváří ZIP klientsky (stáhne DOCX + obrázky, zabalí).
- Backend má endpoint `POST /cases/{id}/exports/case-zip`.
- Klientská varianta funguje, ale duplikuje logiku serveru. Zvážit migraci v kroku 7.

### Bez rizika (potvrzeno auditem)

- API kontrakty pro všechny aktivní endpointy jsou správně naparsovány.
- `ProjectSummary` nemá `source` pole — ale desktop-qt `source` čte až z `ProjectDetail` (správně).
- `ExportCreateResponse.exportId` → `GET /exports/{id}` → `ExportRead.downloadUrl` — tok správně implementován.
