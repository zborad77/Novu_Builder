from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def request_json_or_text(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 5,
) -> tuple[int, Any]:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, _decode_body(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, _decode_body(raw)
    except socket.timeout:
        return 0, f"request timed out after {timeout}s"
    except urllib.error.URLError as exc:
        return 0, f"connection error: {exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive last resort
        return 0, f"unexpected error: {exc}"


def print_results(results: list[CheckResult], *, title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for result in results:
        marker = "OK" if result.ok else "FAIL"
        suffix = f"  [{result.detail}]" if result.detail else ""
        print(f"{marker:<4} {result.name}{suffix}")


def all_ok(results: list[CheckResult]) -> bool:
    return all(result.ok for result in results)


def _decode_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
