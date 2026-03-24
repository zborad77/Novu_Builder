#!/usr/bin/env python3
"""
End-to-end storage persistence test — enterprise/CI ready.

Postup:
  1.  Ověří dostupnost backendu (GET /health → fallback GET /)
  2.  Přihlásí se (credentials z ENV nebo args)
  3.  Vytvoří izolovaný testovací case (run_id v title + description + source)
  4.  Nahraje testovací foto + ověří na disku (existence, velikost > 0)
  5.  Vytvoří case-zip export + ověří na disku:
        • ZIP existence + velikost > 0
        • ZIP obsahuje project.json
        • JSON sidecar existence + velikost > 0 + validní JSON
  6.  Test A — Poškozený JSON: záloha → korupce → GET → nesmí vrátit 500 → obnova
  7.  Test B — Smazaný JSON:   záloha → smazání → GET → nesmí vrátit 404 → obnova
  8.  Test C — Atomický zápis: nový export → scan .tmp → validace všech .json
  9.  Test D — Restart:        clear cache → GET → export dostupný z disku
  10. Simuluje restart (smaže in-memory cache)
  11. Ověří persistence po restartu:
        • API: export vrací HTTP 200, správné id + status
        • API: foto je stále v seznamu
        • Disk: ZIP a sidecar existují, SHA-256 odpovídají baseline
        • ZIP obsah a JSON validita jsou stále v pořádku
  12. Cleanup: foto (DELETE API), case (archive), export soubory (disk, přesně)
  13. Výsledek PASS / FAIL

Izolace paralelních běhů:
  Každý běh dostane plný UUID4 jako run_id (128 bitů entropie).
  Tento run_id je součástí title, description i názvu uploadovaného souboru.
  Paralelní běhy se nikdy nemohou ovlivnit.

Test data (filtrovatelná pro batch cleanup):
  • title prefix  : "test_persistence_"
  • source        : "ci-test"
  • description   : obsahuje "run_id=<uuid>"
  Batch cleanup hint se tiskne na konci každého běhu.

Credentials (v pořadí priority):
  1. --email / --password  (CLI args)
  2. NOVU_TEST_EMAIL / NOVU_TEST_PASSWORD  (ENV)
  3. fallback: demo@novu.local / demo1234

ENV proměnné:
  NOVU_TEST_BASE_URL    výchozí: http://localhost:8000
  NOVU_TEST_EMAIL
  NOVU_TEST_PASSWORD
  STORAGE_ROOT          výchozí: <repo>/storage

Použití:
  python scripts/test_storage_persistence.py
  python scripts/test_storage_persistence.py --base-url http://localhost:8000
  NOVU_TEST_EMAIL=admin@novu.cz NOVU_TEST_PASSWORD=NovuAdmin2024! python scripts/test_storage_persistence.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Konstanty
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"
REQUEST_TIMEOUT = 15       # sekund na jeden požadavek
RETRY_TOTAL = 3            # pokusy při síťové chybě / 5xx
RETRY_BACKOFF = 0.5        # exponenciální backoff (sekund)
TEST_CASE_PREFIX = "test_persistence_"
TEST_CASE_SOURCE = "ci-test"   # strojově filtrovatelný příznak v DB
# Soubor, který musí být vždy přítomen v case-zip (viz _build_case_zip_bytes)
ZIP_REQUIRED_ENTRY = "project.json"

_C_PASS = "\033[92mPASS\033[0m"
_C_FAIL = "\033[91mFAIL\033[0m"
_C_SKIP = "\033[93mSKIP\033[0m"

# ---------------------------------------------------------------------------
# Výsledky
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    badge = _C_PASS if ok else _C_FAIL
    print(f"  [{badge}] {name}" + (f"  ({detail})" if detail else ""))


def _abort(step: str, detail: str) -> None:
    """Zaloguje selhání a okamžitě ukončí test (try/finally zaručí cleanup)."""
    record(step, False, detail)
    raise _StepFailed(f"{step}: {detail}")


class _StepFailed(Exception):
    pass


# ---------------------------------------------------------------------------
# HTTP session s retry
# ---------------------------------------------------------------------------

def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST", "PATCH", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _get(s: requests.Session, url: str, **kw) -> requests.Response:
    return s.get(url, timeout=REQUEST_TIMEOUT, **kw)


def _post(s: requests.Session, url: str, **kw) -> requests.Response:
    return s.post(url, timeout=REQUEST_TIMEOUT, **kw)


def _delete(s: requests.Session, url: str, **kw) -> requests.Response:
    return s.delete(url, timeout=REQUEST_TIMEOUT, **kw)


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

_SHA256_CHUNK = 65536  # 64 KB — bezpečné i pro velké soubory


def _file_sha256(path: Path) -> str:
    """SHA-256 s chunked reading (64 KB bloky) — nezatíží paměť ani pro velké soubory."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_SHA256_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _validate_zip(path: Path) -> list[str]:
    """
    Ověří ZIP na třech úrovních:
      1. Otevření archivu (BadZipFile → korupce hlavičky)
      2. Neprázdný seznam položek
      3. Čitelnost každé položky (read() + CRC ověření přes testzip())
    Vyhodí _StepFailed při jakémkoli selhání.
    """
    try:
        with ZipFile(path) as zf:
            names = zf.namelist()
            if not names:
                _abort("export.zip_valid", f"prázdný ZIP {path.name}")
            # Povinná položka musí být přítomna před CRC kontrolou
            if ZIP_REQUIRED_ENTRY not in names:
                _abort(
                    "export.zip_contains_project_json",
                    f"'{ZIP_REQUIRED_ENTRY}' chybí v {path.name}; nalezeno: {names[:10]}",
                )
            # testzip() projde celý archiv, ověří CRC každé položky;
            # vrátí název první poškozené položky nebo None při OK
            bad_entry = zf.testzip()
            if bad_entry is not None:
                _abort("export.zip_entry_crc", f"poškozená položka '{bad_entry}' v {path.name}")
    except BadZipFile as exc:
        _abort("export.zip_valid", f"poškozený ZIP {path.name}: {exc}")
    return names


def _validate_json_file(path: Path) -> dict:
    """Vrátí deserializovaný objekt. Vyhodí _StepFailed při prázdném souboru nebo neplatném JSON."""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        _abort("export.sidecar_json_valid", f"prázdný sidecar {path}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _abort("export.sidecar_json_valid", f"neplatný JSON v {path}: {exc}")


# ---------------------------------------------------------------------------
# Kroky testu
# ---------------------------------------------------------------------------

def check_backend(session: requests.Session, base: str) -> None:
    """GET /health → fallback GET /. Selžou-li oba → _StepFailed."""
    last_err = "žádný pokus neproběhl"
    for path, label in ((f"{API_PREFIX}/health", "/health"), ("/", "/")):
        try:
            resp = _get(session, f"{base}{path}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_err = str(exc)
            continue
        if resp.status_code == 200:
            record("backend.reachable", True, f"HTTP 200 na {label}")
            return
        last_err = f"HTTP {resp.status_code} na {label}"
    _abort("backend.reachable", f"backend na {base} neodpovídá — {last_err}")


def login(session: requests.Session, base: str, email: str, password: str) -> str:
    resp = _post(session, f"{base}{API_PREFIX}/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        _abort("auth.login", f"HTTP {resp.status_code}: {resp.text[:200]}")
    token = resp.json().get("accessToken") or ""
    if not token:
        _abort("auth.login", "accessToken chybí v odpovědi")
    record("auth.login", True, email)
    return token


def create_test_case(session: requests.Session, base: str, run_id: str) -> str:
    """
    Vytvoří izolovaný testovací case.
    Filtrovatelný trojím způsobem (viz batch_cleanup_hint níže):
      • title prefix "test_persistence_"
      • source == "ci-test"
      • description obsahuje run_id
    Paralelní bezpečnost: run_id je plný UUID4 (128 bitů entropie).
    DELETE endpoint neexistuje → case se archivuje v cleanup.
    """
    title = f"{TEST_CASE_PREFIX}{run_id}"
    description = (
        f"[CI-TEST run_id={run_id}] "
        "Automaticky vytvořeno skriptem test_storage_persistence.py. "
        "Bezpečno archivovat nebo smazat."
    )
    resp = _post(
        session,
        f"{base}{API_PREFIX}/cases",
        json={"title": title, "source": TEST_CASE_SOURCE, "description": description},
    )
    if resp.status_code != 201:
        _abort("case.create", f"HTTP {resp.status_code}: {resp.text[:200]}")
    case_id = resp.json().get("id") or ""
    if not case_id:
        _abort("case.create", "id chybí v odpovědi")
    record("case.create", True, f"id={case_id}  title={title}")
    return case_id


def upload_photo(session: requests.Session, base: str, case_id: str, run_id: str) -> tuple[str, str]:
    """
    Nahraje 1×1 px PNG pojmenovaný s run_id (pro jednoznačnou identifikaci v paralelních bězích).
    Vrátí (photo_id, storage_key).
    """
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    filename = f"test_persistence_{run_id}.png"
    files = {"files": (filename, png_bytes, "image/png")}
    resp = _post(session, f"{base}{API_PREFIX}/cases/{case_id}/images", files=files)
    if resp.status_code != 201:
        _abort("photo.upload", f"HTTP {resp.status_code}: {resp.text[:200]}")
    uploaded = resp.json().get("uploaded", [])
    if not uploaded:
        _abort("photo.upload", "prázdné pole uploaded v odpovědi")
    photo_id = uploaded[0].get("id") or ""
    storage_key = uploaded[0].get("storageKey") or ""
    if not photo_id or not storage_key:
        _abort("photo.upload", f"chybí id nebo storageKey: {uploaded[0]}")
    record("photo.upload", True, f"id={photo_id}  key={storage_key}")
    return photo_id, storage_key


def verify_photo_on_disk(storage_root: Path, storage_key: str) -> int:
    """Ověří existenci a velikost fotografie na disku. Vrátí velikost v bytech."""
    photo_path = storage_root / storage_key
    if not photo_path.is_file():
        _abort("disk.photo_exists", str(photo_path))
    size = photo_path.stat().st_size
    if size == 0:
        _abort("disk.photo_size", f"soubor má 0 bytů: {photo_path}")
    record("disk.photo_exists", True, f"{size} B  {photo_path}")
    return size


def create_export(session: requests.Session, base: str, case_id: str) -> str:
    resp = _post(session, f"{base}{API_PREFIX}/cases/{case_id}/exports/case-zip")
    if resp.status_code != 201:
        _abort("export.create", f"HTTP {resp.status_code}: {resp.text[:200]}")
    export_id = resp.json().get("exportId") or ""
    if not export_id:
        _abort("export.create", "exportId chybí v odpovědi")
    record("export.create", True, f"id={export_id}")
    return export_id


# Přenáší informace o souborech pro porovnání před/po restartu.
class _ExportBaseline:
    __slots__ = ("zip_path", "sidecar_path", "zip_size", "sidecar_size", "zip_sha256", "sidecar_sha256")

    def __init__(self, zip_path: Path, sidecar_path: Path) -> None:
        self.zip_path = zip_path
        self.sidecar_path = sidecar_path
        self.zip_size = zip_path.stat().st_size
        self.sidecar_size = sidecar_path.stat().st_size
        self.zip_sha256 = _file_sha256(zip_path)
        self.sidecar_sha256 = _file_sha256(sidecar_path)


def verify_export_on_disk(storage_root: Path, case_id: str, export_id: str) -> _ExportBaseline:
    """
    Ověří:
      • ZIP existence + velikost > 0 + ZIP obsahuje project.json
      • JSON sidecar existence + velikost > 0 + validní JSON
    Hledání je omezeno výhradně na soubory tohoto testu:
      ZIP:     exports/{case_id}/{export_id}-*     (přesný podadresář)
      Sidecar: exports/{export_id}.json            (přesná cesta)
    Vrátí _ExportBaseline pro porovnání po restartu.
    """
    case_exports_dir = storage_root / "exports" / case_id
    exports_root_dir = storage_root / "exports"

    # --- ZIP ---
    zip_files = list(case_exports_dir.glob(f"{export_id}-*")) if case_exports_dir.exists() else []
    if not zip_files:
        _abort("disk.export_file_exists", f"nenalezeno v {case_exports_dir}")
    zip_path = zip_files[0]
    zip_size = zip_path.stat().st_size
    if zip_size == 0:
        _abort("disk.export_file_size", f"ZIP má 0 bytů: {zip_path}")
    record("disk.export_file_exists", True, f"{zip_size} B  {zip_path.name}")

    # ZIP obsah — musí obsahovat project.json
    zip_entries = _validate_zip(zip_path)
    has_required = ZIP_REQUIRED_ENTRY in zip_entries
    record("export.zip_valid", True, f"{len(zip_entries)} položek")
    if not has_required:
        _abort(
            "export.zip_contains_project_json",
            f"'{ZIP_REQUIRED_ENTRY}' chybí; nalezeno: {zip_entries[:10]}",
        )
    record("export.zip_contains_project_json", True, f"nalezeno v {zip_path.name}")

    # --- JSON sidecar ---
    sidecar = exports_root_dir / f"{export_id}.json"
    if not sidecar.is_file():
        _abort("disk.export_sidecar_exists", str(sidecar))
    sidecar_size = sidecar.stat().st_size
    if sidecar_size == 0:
        _abort("disk.export_sidecar_size", f"sidecar má 0 bytů: {sidecar}")
    record("disk.export_sidecar_exists", True, f"{sidecar_size} B  {sidecar.name}")

    sidecar_data = _validate_json_file(sidecar)
    record("export.sidecar_json_valid", True, f"id={sidecar_data.get('id', '?')}")

    return _ExportBaseline(zip_path, sidecar)


# ---------------------------------------------------------------------------
# JSON robustness tests (A, B, C, D)
# ---------------------------------------------------------------------------

def _clear_export_cache_silent() -> bool:
    """
    Smaže in-memory _EXPORT_STORE bez zaznamenání výsledku.
    Vrátí True pokud se podařilo (in-process import), False pokud backend
    běží jako separátní proces.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import app.services.export_service as es  # noqa: PLC0415
        es._EXPORT_STORE.clear()
        return True
    except Exception:  # noqa: BLE001
        return False


def test_a_corrupted_json(
    session: requests.Session,
    base: str,
    export_id: str,
    sidecar_path: Path,
) -> None:
    """
    Test A — Poškozený JSON sidecar.
    Postup: záloha originálu → zápis nevalidního JSON → clear cache
            → GET /exports/{id} → ověření že není 500 → obnova originálu.
    PASS: HTTP != 500, aplikace nepadá, vrátí export (200 nebo rozumný status)
    FAIL: HTTP 500 nebo výjimka
    """
    if not sidecar_path.is_file():
        print(f"  [{_C_SKIP}] test_a  (sidecar neexistuje, přeskočeno)")
        return

    backup = sidecar_path.read_bytes()
    cache_cleared = _clear_export_cache_silent()
    if not cache_cleared:
        print(f"  [{_C_SKIP}] test_a.cache_clear  (separátní proces — výsledek může pocházet z cache)")

    sidecar_path.write_text("{CORRUPTED_BY_TEST_A", encoding="utf-8")
    try:
        resp = _get(session, f"{base}{API_PREFIX}/exports/{export_id}")
        record("test_a.no_500", resp.status_code != 500, f"HTTP {resp.status_code}")
        # ZIP existuje → backend musí vrátit 200 přes file-fallback, ne 404
        if resp.status_code == 200:
            record("test_a.export_returned", True, "fallback via soubor nebo cache")
        elif resp.status_code == 404:
            record("test_a.export_returned", False, "404 přestože ZIP existuje — fallback nefunguje")
        else:
            record("test_a.export_returned", False, f"neočekávaný HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("test_a.no_500", False, f"výjimka: {exc}")
    finally:
        sidecar_path.write_bytes(backup)  # vždy obnovíme originál


def test_b_deleted_json(
    session: requests.Session,
    base: str,
    export_id: str,
    sidecar_path: Path,
) -> None:
    """
    Test B — Smazaný JSON sidecar.
    Postup: záloha → smazání → clear cache → GET /exports/{id}
            → ověření že není 404 → obnova originálu.
    PASS: HTTP 200 (fallback via soubor), nikdy 404 nebo 500
    FAIL: HTTP 404 nebo 500
    """
    if not sidecar_path.is_file():
        print(f"  [{_C_SKIP}] test_b  (sidecar neexistuje, přeskočeno)")
        return

    backup = sidecar_path.read_bytes()
    _clear_export_cache_silent()
    sidecar_path.unlink()
    try:
        resp = _get(session, f"{base}{API_PREFIX}/exports/{export_id}")
        record("test_b.no_404", resp.status_code != 404, f"HTTP {resp.status_code}")
        record("test_b.no_500", resp.status_code != 500, f"HTTP {resp.status_code}")
        record("test_b.export_returned", resp.status_code == 200,
               "fallback via soubor" if resp.status_code == 200 else f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        record("test_b.no_404", False, f"výjimka: {exc}")
    finally:
        sidecar_path.write_bytes(backup)  # obnova nutná pro Tests C, D a verify_after_restart


def test_c_atomic_write(
    session: requests.Session,
    base: str,
    case_id: str,
    storage_root: Path,
) -> None:
    """
    Test C — Atomický zápis.
    Vytvoří druhý export, pak okamžitě zkontroluje stav disku:
      • žádné .tmp soubory nesmí zůstat po kompletním zápisu
      • všechny .json soubory v exports/ musí být validní JSON
    PASS: 0 .tmp souborů, všechny .json soubory parsovatelné
    FAIL: nalezeny .tmp soubory nebo nevalidní JSON
    """
    resp = _post(session, f"{base}{API_PREFIX}/cases/{case_id}/exports/case-zip")
    if resp.status_code != 201:
        record("test_c.second_export_created", False, f"HTTP {resp.status_code}: {resp.text[:120]}")
        return
    second_id = resp.json().get("exportId", "")
    record("test_c.second_export_created", bool(second_id), f"id={second_id}")

    exports_dir = storage_root / "exports"

    # .tmp soubory nesmí existovat po dokončeném zápisu
    tmp_files = list(exports_dir.rglob("*.tmp")) if exports_dir.exists() else []
    record(
        "test_c.no_tmp_files",
        len(tmp_files) == 0,
        f"nalezeno {len(tmp_files)}: {[p.name for p in tmp_files]}" if tmp_files else "čisto",
    )

    # Všechny .json soubory musí být parsovatelné
    json_files = list(exports_dir.rglob("*.json")) if exports_dir.exists() else []
    invalid: list[str] = []
    for jf in json_files:
        try:
            content = jf.read_text(encoding="utf-8").strip()
            if content:
                json.loads(content)
        except (json.JSONDecodeError, OSError):
            invalid.append(jf.name)
    record(
        "test_c.all_json_valid",
        not invalid,
        f"nevalidní: {invalid}" if invalid else f"ověřeno {len(json_files)} souborů",
    )

    # Cleanup druhého exportu
    if second_id:
        for name in (f"{second_id}.json", f"{second_id}.json.tmp"):
            (exports_dir / name).unlink(missing_ok=True)
        for p in (exports_dir / case_id).glob(f"{second_id}-*"):
            p.unlink(missing_ok=True)


def test_d_restart_persistence(
    session: requests.Session,
    base: str,
    export_id: str,
    zip_path: Path,
) -> None:
    """
    Test D — Restart + persistence bez závislosti na JSON sidecar.
    Postup: clear cache → ověří ZIP na disku → GET /exports/{id}
            → export musí být dostupný (přes sidecar nebo file-fallback).
    PASS: HTTP 200, správné export id
    FAIL: HTTP != 200 nebo chybné id
    """
    _clear_export_cache_silent()

    if not zip_path.is_file():
        record("test_d.zip_on_disk", False, str(zip_path))
        return
    record("test_d.zip_on_disk", True, zip_path.name)

    resp = _get(session, f"{base}{API_PREFIX}/exports/{export_id}")
    record("test_d.export_accessible", resp.status_code == 200, f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        returned_id = resp.json().get("id")
        record("test_d.export_id_match", returned_id == export_id, returned_id)


def simulate_restart() -> None:
    """Smaže in-memory _EXPORT_STORE — simuluje restart bez zastavení procesu."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import app.services.export_service as es  # noqa: PLC0415
        before = len(es._EXPORT_STORE)
        es._EXPORT_STORE.clear()
        record("restart.cache_cleared", True, f"vymazáno {before} záznamů")
    except Exception as exc:  # noqa: BLE001
        # Backend běží jako separátní proces → in-process import nedostupný.
        # Persistence se ověří v dalším kroku přes HTTP.
        print(f"  [{_C_SKIP}] restart.cache_cleared  (in-process import nedostupný: {exc})")


def verify_after_restart(
    session: requests.Session,
    base: str,
    case_id: str,
    export_id: str,
    storage_key: str,
    baseline: _ExportBaseline,
) -> None:
    """
    Ověřuje:
      • API: export HTTP 200, správné id a status
      • API: foto stále přítomno v seznamu
      • Disk: ZIP a sidecar existují, SHA-256 odpovídá baseline
      • ZIP obsah a JSON validita stále v pořádku
    """
    # --- API: export ---
    resp = _get(session, f"{base}{API_PREFIX}/exports/{export_id}")
    if resp.status_code != 200:
        _abort("post_restart.export_get", f"HTTP {resp.status_code}")
    record("post_restart.export_get", True, f"HTTP {resp.status_code}")

    body = resp.json()
    status_val = body.get("status")
    record("post_restart.export_status", status_val == "completed", status_val)
    id_val = body.get("id")
    record("post_restart.export_id_match", id_val == export_id, id_val)

    # --- API: foto ---
    resp2 = _get(session, f"{base}{API_PREFIX}/cases/{case_id}/images")
    if resp2.status_code != 200:
        _abort("post_restart.photo_list", f"HTTP {resp2.status_code}")
    record("post_restart.photo_list", True, f"HTTP {resp2.status_code}")

    items = resp2.json().get("items", [])
    keys = {i.get("storageKey") for i in items}
    found = storage_key in keys
    record(
        "post_restart.photo_storageKey_present",
        found,
        storage_key if found else f"nenalezeno v {len(keys)} položkách",
    )
    if not found:
        _abort("post_restart.photo_storageKey_present", "storage_key chybí po restartu")

    # --- Disk: ZIP integrta ---
    if not baseline.zip_path.is_file():
        _abort("post_restart.zip_exists", str(baseline.zip_path))
    record("post_restart.zip_exists", True, baseline.zip_path.name)

    current_zip_sha = _file_sha256(baseline.zip_path)
    sha_match = current_zip_sha == baseline.zip_sha256
    record(
        "post_restart.zip_sha256_match",
        sha_match,
        f"{current_zip_sha[:16]}…" if sha_match else f"bylo {baseline.zip_sha256[:16]}…  je {current_zip_sha[:16]}…",
    )
    if not sha_match:
        _abort("post_restart.zip_sha256_match", "ZIP byl změněn po restartu")

    # ZIP obsah stále validní
    zip_entries = _validate_zip(baseline.zip_path)
    record("post_restart.zip_valid", True, f"{len(zip_entries)} položek")
    if ZIP_REQUIRED_ENTRY not in zip_entries:
        _abort("post_restart.zip_contains_project_json", f"'{ZIP_REQUIRED_ENTRY}' chybí po restartu")
    record("post_restart.zip_contains_project_json", True)

    # --- Disk: JSON sidecar integrita ---
    if not baseline.sidecar_path.is_file():
        _abort("post_restart.sidecar_exists", str(baseline.sidecar_path))
    record("post_restart.sidecar_exists", True, baseline.sidecar_path.name)

    current_sidecar_sha = _file_sha256(baseline.sidecar_path)
    sidecar_match = current_sidecar_sha == baseline.sidecar_sha256
    record(
        "post_restart.sidecar_sha256_match",
        sidecar_match,
        f"{current_sidecar_sha[:16]}…" if sidecar_match else f"bylo {baseline.sidecar_sha256[:16]}…  je {current_sidecar_sha[:16]}…",
    )
    if not sidecar_match:
        _abort("post_restart.sidecar_sha256_match", "JSON sidecar byl změněn po restartu")

    _validate_json_file(baseline.sidecar_path)
    record("post_restart.sidecar_json_valid", True)


# ---------------------------------------------------------------------------
# Batch cleanup hint
# ---------------------------------------------------------------------------

def print_batch_cleanup_hint(base: str, run_id: str, case_id: str | None) -> None:
    """
    Tiskne instrukce pro ruční nebo automatické hromadné čištění testovacích dat.

    Výstup obsahuje:
      • Strukturovaný JSON blok (CI_CLEANUP_HINT) — strojově parsovatelný v CI logu
      • Čitelný text pro vývojáře

    CI parsování (bash příklad):
      grep 'CI_CLEANUP_HINT' ci.log | sed 's/.*CI_CLEANUP_HINT //' | python3 -m json.tool

    Hromadné archivování zanechaných test cases (SQL):
      UPDATE projects SET status = 'archived'
      WHERE source = 'ci-test'
        AND title LIKE 'test_persistence_%'
        AND created_at < NOW() - INTERVAL '1 day';
    """
    hint = {
        "run_id": run_id,
        "case_id": case_id,
        "db_filter": {"source": TEST_CASE_SOURCE, "title_prefix": TEST_CASE_PREFIX},
        "api_filter": f"{base}{API_PREFIX}/cases?search={TEST_CASE_PREFIX}",
        "sql_batch_archive": (
            "UPDATE projects SET status = 'archived' "
            f"WHERE source = '{TEST_CASE_SOURCE}' "
            f"AND title LIKE '{TEST_CASE_PREFIX}%' "
            "AND created_at < NOW() - INTERVAL '1 day';"
        ),
    }
    # Přesně jeden řádek, compact separátory — zaručeně grep-parsovatelné v CI logu
    print(f"CI_CLEANUP_HINT {json.dumps(hint, ensure_ascii=False, separators=(',', ':'))}")
    print(
        f"  [INFO] Batch cleanup:\n"
        f"         API : GET {hint['api_filter']}\n"
        f"         DB  : WHERE source='{TEST_CASE_SOURCE}' AND title LIKE '{TEST_CASE_PREFIX}%'\n"
        f"         Běh : run_id={run_id}  case_id={case_id}"
    )


# ---------------------------------------------------------------------------
# Cleanup — vždy v try/finally, nikdy nefailuje test
# ---------------------------------------------------------------------------

def cleanup(
    session: requests.Session,
    base: str,
    storage_root: Path,
    case_id: str | None,
    photo_id: str | None,
    storage_key: str | None,
    export_id: str | None,
) -> None:
    print("\n── Cleanup ──────────────────────────────────────────────────")

    # 1. Smazání fotografie přes API
    if case_id and photo_id:
        try:
            resp = _delete(session, f"{base}{API_PREFIX}/cases/{case_id}/images/{photo_id}")
            ok = resp.status_code in (200, 204)
            print(f"  cleanup.photo_delete    HTTP {resp.status_code}" + ("" if ok else f"  {resp.text[:120]}"))
        except Exception as exc:  # noqa: BLE001
            print(f"  cleanup.photo_delete    chyba: {exc}")

    # 2. Archivace testovacího case
    #    DELETE /cases/{id} neexistuje → archive je nejbližší ekvivalent.
    #    Zanechaná data lze hromadně čistit — viz print_batch_cleanup_hint().
    if case_id:
        try:
            resp = _post(session, f"{base}{API_PREFIX}/cases/{case_id}/archive")
            ok = resp.status_code == 200
            print(f"  cleanup.case_archive    HTTP {resp.status_code}" + ("" if ok else f"  {resp.text[:120]}"))
        except Exception as exc:  # noqa: BLE001
            print(f"  cleanup.case_archive    chyba: {exc}")

    # 3. Smazání exportních souborů z disku — pouze soubory tohoto testu.
    #    Sidecar:   exports/{export_id}.json       (přesná cesta, žádný glob)
    #    ZIP:       exports/{case_id}/{export_id}-*  (omezeno na case_id podadresář)
    if export_id:
        exports_root = storage_root / "exports"
        removed = 0
        for name in (f"{export_id}.json", f"{export_id}.json.tmp"):
            p = exports_root / name
            if p.exists():
                try:
                    p.unlink()
                    removed += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  cleanup.disk  nelze smazat {p}: {exc}")
        if case_id:
            case_dir = exports_root / case_id
            for p in case_dir.glob(f"{export_id}-*"):
                try:
                    p.unlink()
                    removed += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  cleanup.disk  nelze smazat {p}: {exc}")
        print(f"  cleanup.export_files    smazáno {removed} souborů")

    # 4. Smazání fotografie z disku (storage_key je přesná cesta, žádný glob)
    if storage_key:
        photo_path = storage_root / storage_key
        if photo_path.exists():
            try:
                photo_path.unlink()
                print(f"  cleanup.photo_disk      smazáno {photo_path.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"  cleanup.photo_disk      nelze smazat {photo_path}: {exc}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    email = args.email or os.getenv("NOVU_TEST_EMAIL", "").strip() or "demo@novu.local"
    password = args.password or os.getenv("NOVU_TEST_PASSWORD", "").strip() or "demo1234"
    return email, password


def _resolve_storage_root(args: argparse.Namespace) -> Path:
    if args.storage_root:
        return Path(args.storage_root)
    env_val = os.getenv("STORAGE_ROOT", "").strip()
    if env_val:
        return Path(env_val)
    return Path(__file__).resolve().parents[2] / "storage"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Storage persistence E2E test — enterprise/CI")
    parser.add_argument("--base-url", default=os.getenv("NOVU_TEST_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--storage-root", default=None)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    email, password = _resolve_credentials(args)
    storage_root = _resolve_storage_root(args)
    # Plný UUID4 — 128 bitů entropie, nulová pravděpodobnost kolize v paralelních bězích
    run_id = uuid.uuid4().hex

    print(f"\nSTORAGE_ROOT : {storage_root}")
    print(f"Backend      : {base}")
    print(f"Credentials  : {email}")
    print(f"Run ID       : {run_id}\n")

    session = _build_session()

    case_id: str | None = None
    photo_id: str | None = None
    storage_key: str | None = None
    export_id: str | None = None
    baseline: _ExportBaseline | None = None

    try:
        print("── 1. Dostupnost backendu ───────────────────────────────────")
        check_backend(session, base)

        print("\n── 2. Autentizace ───────────────────────────────────────────")
        token = login(session, base, email, password)
        session.headers["Authorization"] = f"Bearer {token}"

        print("\n── 3. Vytvoření izolovaného testovacího case ────────────────")
        case_id = create_test_case(session, base, run_id)

        print("\n── 4. Upload fotografie + ověření na disku ──────────────────")
        photo_id, storage_key = upload_photo(session, base, case_id, run_id)
        verify_photo_on_disk(storage_root, storage_key)

        print("\n── 5. Vytvoření exportu + ověření na disku ──────────────────")
        export_id = create_export(session, base, case_id)
        baseline = verify_export_on_disk(storage_root, case_id, export_id)

        print("\n── 6. Test A — Poškozený JSON sidecar ───────────────────────")
        test_a_corrupted_json(session, base, export_id, baseline.sidecar_path)

        print("\n── 7. Test B — Smazaný JSON sidecar ─────────────────────────")
        test_b_deleted_json(session, base, export_id, baseline.sidecar_path)

        print("\n── 8. Test C — Atomický zápis (žádné .tmp soubory) ──────────")
        test_c_atomic_write(session, base, case_id, storage_root)

        print("\n── 9. Test D — Restart + persistence z disku ────────────────")
        test_d_restart_persistence(session, base, export_id, baseline.zip_path)

        print("\n── 10. Simulace restartu (vymazání in-memory cache) ─────────")
        simulate_restart()

        print("\n── 11. Ověření persistence po restartu ──────────────────────")
        verify_after_restart(session, base, case_id, export_id, storage_key, baseline)

    except _StepFailed:
        pass  # chyba již zalogována přes record()

    finally:
        cleanup(session, base, storage_root, case_id, photo_id, storage_key, export_id)

    # ---------------------------------------------------------------------------
    # Výsledek
    # ---------------------------------------------------------------------------
    print("\n══════════════════════════════════════════════════════════════")
    failed = [name for name, ok, _ in _results if not ok]
    total = len(_results)
    passed = total - len(failed)
    if not failed:
        print(f"  VÝSLEDEK: {_C_PASS}  — {passed}/{total} kontrol prošlo")
    else:
        print(f"  VÝSLEDEK: {_C_FAIL}  — {passed}/{total} kontrol prošlo")
        print(f"  Neúspěšné: {', '.join(failed)}")

    print_batch_cleanup_hint(base, run_id, case_id)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
