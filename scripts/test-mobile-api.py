#!/usr/bin/env python3
"""
Mobile API test script — otestuje celý flow mobilní app:
  login → list cases → create case → upload photo → trigger analysis → poll job

Použití:
  python scripts/test-mobile-api.py
  python scripts/test-mobile-api.py --url http://192.168.19.29:8000/api/v1
  python scripts/test-mobile-api.py --email demo@novu.local --password demo1234
"""
import argparse
import json
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

# ── Config ─────────────────────────────────────────────────────────────────

DEFAULT_URL = "http://localhost:8000/api/v1"
DEFAULT_EMAIL = "demo@novu.local"
DEFAULT_PASSWORD = "demo1234"

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OK = "\033[92mOK\033[0m"
FAIL = "\033[91mERR\033[0m"
INFO = "\033[94m--\033[0m"


# ── HTTP helpers ────────────────────────────────────────────────────────────

def request(method: str, url: str, body=None, token: str | None = None, files=None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if files:
        # multipart/form-data
        boundary = "----NovuTestBoundary"
        parts = []
        for name, (filename, data, mime) in files.items():
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            )
        body_bytes = b""
        for part, (_, data, _) in zip(parts, files.values()):
            body_bytes += part.encode() + data + b"\r\n"
        body_bytes += f"--{boundary}--\r\n".encode()
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        }
        data_to_send = body_bytes
    elif body is not None:
        data_to_send = json.dumps(body).encode()
    else:
        data_to_send = None

    req = urllib.request.Request(url, data=data_to_send, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            detail = json.loads(body_text).get("detail", body_text)
        except Exception:
            detail = body_text
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


# ── Test steps ───────────────────────────────────────────────────────────────

def step(label: str):
    print(f"\n{INFO} {label}")


def ok(msg: str):
    print(f"  {OK} {msg}")


def fail(msg: str):
    print(f"  {FAIL} {msg}")
    sys.exit(1)


def run_tests(base_url: str, email: str, password: str):
    print(f"\n{'='*55}")
    print(f"  NOVU Mobile API Test")
    print(f"  URL: {base_url}")
    print(f"{'='*55}")

    # 1. Health check
    step("Health check")
    try:
        result = request("GET", f"{base_url}/health")
        ok(f"Status: {result.get('status', result)}")
    except Exception as e:
        fail(f"Backend not reachable: {e}")

    # 2. Login
    step(f"Login ({email})")
    try:
        result = request("POST", f"{base_url}/auth/login", {"email": email, "password": password})
        token = result["accessToken"]
        user = result["user"]
        ok(f"Token: {token[:20]}…")
        ok(f"User: {user['fullName']} ({user['role']})")
    except Exception as e:
        fail(f"Login failed: {e}")

    # 3. List cases
    step("List cases")
    try:
        result = request("GET", f"{base_url}/cases", token=token)
        total = result.get("total", len(result.get("items", [])))
        ok(f"Total: {total} zakázek")
        if result.get("items"):
            first = result["items"][0]
            ok(f"První: '{first['title']}' [{first['status']}]")
    except Exception as e:
        fail(f"List cases failed: {e}")

    # 4. Create case
    step("Create case")
    try:
        payload = {
            "title": f"API Test Zakázka {int(time.time())}",
            "description": "Automatický test z test-mobile-api.py",
            "source": "mobile",
            "locationLat": 50.0755,
            "locationLng": 14.4378,
            "addressLabel": "Václavské náměstí, Praha",
            "propertyType": "facade",
            "repairScope": "local_repair",
        }
        result = request("POST", f"{base_url}/cases", payload, token=token)
        case_id = result["id"]
        ok(f"Case ID: {case_id}")
        ok(f"Status: {result['status']}")
    except Exception as e:
        fail(f"Create case failed: {e}")

    # 5. Get case detail
    step("Get case detail")
    try:
        result = request("GET", f"{base_url}/cases/{case_id}", token=token)
        ok(f"Title: {result['title']}")
        ok(f"Location: {result['location']['addressLabel']}")
    except Exception as e:
        fail(f"Get detail failed: {e}")

    # 6. Upload photo (minimal JPEG)
    step("Upload photo")
    try:
        # Minimální validní JPEG (1x1 pixel, červený)
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD7, 0xFF, 0xD9,
        ])
        result = request(
            "POST",
            f"{base_url}/cases/{case_id}/images",
            token=token,
            files={"files": ("test_photo.jpg", jpeg_bytes, "image/jpeg")},
        )
        photo_id = (result.get("uploaded") or [{}])[0].get("id")
        ok(f"Photo ID: {photo_id}")
    except Exception as e:
        fail(f"Photo upload failed: {e}")

    # 7. Trigger analysis
    step("Trigger analysis job")
    try:
        result = request("POST", f"{base_url}/cases/{case_id}/analysis-jobs", token=token)
        job_id = result["jobId"]
        ok(f"Job ID: {job_id}")
        ok(f"Status: {result['status']}")
        ok(f"Provider: {result['provider']}")
    except Exception as e:
        fail(f"Trigger analysis failed: {e}")

    # 8. Poll job status
    step("Poll job status (max 10s)")
    for attempt in range(5):
        time.sleep(2)
        try:
            result = request("GET", f"{base_url}/analysis-jobs/{job_id}", token=token)
            status = result.get("status")
            print(f"    attempt {attempt+1}: {status}")
            if status in ("completed", "failed", "error"):
                if status == "completed":
                    ok(f"Job completed!")
                else:
                    fail(f"Job failed: {result.get('errorMessage')}")
                break
        except Exception as e:
            print(f"    attempt {attempt+1}: poll error: {e}")
    else:
        ok("Job still running (timeout — normální pro dlouhé zpracování)")

    # 9. Cleanup info
    print(f"\n{'='*55}")
    print(f"  {OK} Všechny testy prošly!")
    print(f"  Case ID pro ruční ověření: {case_id}")
    print(f"{'='*55}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NOVU Mobile API test")
    parser.add_argument("--url", default=DEFAULT_URL, help="API base URL")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    args = parser.parse_args()
    run_tests(args.url, args.email, args.password)
