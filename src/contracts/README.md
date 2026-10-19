# Sdílené API kontrakty

Strojově čitelné kontrakty mezi backendem a klienty (web, desktop). Generuje je
backend, klienti je čtou; **backend je za běhu nečte**.

| Soubor | Zdroj | Generátor | Kontrola |
|---|---|---|---|
| `openapi/openapi.json` | FastAPI aplikace | `python -m scripts.export_contracts` (z adresáře backendu) | `tests/architecture/test_baselines.py` |
| `openapi/routes.snapshot.json` | routy v pořadí registrace | totéž | totéž |

Interní bezpečnostní konfigurace (exposure tabulka, gateway allowlist, tajné klíče)
zůstává v backendu a `docs/security/` (rozhodnutí O3).

Jakákoli změna těchto souborů je **změna veřejného API** a vyžaduje schválení.
Během modulárního refaktoru je povolena nulová změna.
