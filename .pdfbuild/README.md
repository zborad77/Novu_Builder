# PDF build — NOVU_MASTER_PRODUCT_BOOK

Generuje `NOVU_MASTER_PRODUCT_BOOK.pdf` z `NOVU_MASTER_PRODUCT_BOOK.md`.
Markdown → HTML (marked) s vykreslením Mermaid diagramů → PDF přes headless Chrome (puppeteer-core).

## Předpoklady
- Node.js (testováno na v24)
- Nainstalovaný Google Chrome (`C:/Program Files/Google/Chrome/Application/chrome.exe`)

## Závislosti (gitignored node_modules)
```
npm install marked@12 puppeteer-core@23 mermaid@11
```

## Spuštění
```
node .pdfbuild/build.mjs
```

Po každé editaci `NOVU_MASTER_PRODUCT_BOOK.md` stačí skript spustit znovu.

## Výstup
- `NOVU_MASTER_PRODUCT_BOOK.pdf` — A4, číslování stran, vykreslené diagramy
- `.pdfbuild/book.html` — mezivýstup (lze smazat)
