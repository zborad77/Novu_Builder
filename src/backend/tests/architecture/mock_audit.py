"""Opt-in pytest plugin: audit účinnosti mocků (modulární refaktor, požadavek 7).

Refaktor přepisuje stringové cíle `patch("app.x.y.NAME")` a
`monkeypatch.setattr("app.x.y.NAME", ...)`. Patch, který po přesunu kódu míří do
modulu, kde se jméno už nehledá, test neselže – jen přestane cokoli testovat.

Plugin u každého patche zaznamená test, cíl a hlavně to, zda byl vložený mock
během testu skutečně zavolán. Porovnání baseline × po refaktoru
(`tools/refactor/compare_mock_audit.py`) pak odhalí každý mock, který dřív byl
zavolán a teď už ne.

    NC_MOCK_AUDIT_OUT=mock_audit.json python -m pytest tests/ -p tests.architecture.mock_audit
"""
from __future__ import annotations

import json
import os
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from _pytest.monkeypatch import notset

_RECORDS: list[dict[str, Any]] = []
_TRACKED: list[tuple[dict[str, Any], Any]] = []
_CURRENT: dict[str, str | None] = {"test": None, "phase": None}


def _test_key(nodeid: str) -> str:
    # Klíč nezávislý na umístění testového souboru (testy se v refaktoru přesouvají).
    path, _, rest = nodeid.partition("::")
    return f"{Path(path).name}::{rest}"


def _is_mock(value: Any) -> bool:
    return isinstance(value, mock.NonCallableMock)


def _record(kind: str, target: str, attribute: str, replacement: Any) -> None:
    test = _CURRENT["test"]
    if test is None:
        return
    entry: dict[str, Any] = {
        "test": test,
        "phase": _CURRENT["phase"],
        "kind": kind,
        "target": target,
        "attribute": attribute,
        "tracked": _is_mock(replacement),
    }
    _RECORDS.append(entry)
    if entry["tracked"]:
        _TRACKED.append((entry, replacement))


_original_enter = mock._patch.__enter__  # type: ignore[attr-defined]


def _audited_enter(self: Any) -> Any:
    result = _original_enter(self)
    try:
        target_obj = self.target
        target = getattr(target_obj, "__name__", None) or type(target_obj).__qualname__
        replacement = result if self.new is mock.DEFAULT else self.new
        kind = "patch" if isinstance(target_obj, types.ModuleType) else "patch.object"
        _record(kind, str(target), str(self.attribute), replacement)
    except Exception:  # pragma: no cover - audit nesmí ovlivnit běh testu
        pass
    return result


_original_setattr = pytest.MonkeyPatch.setattr


def _audited_setattr(self: Any, target: Any, name: Any = notset, value: Any = notset, raising: bool = True) -> None:
    # Stejná signatura jako MonkeyPatch.setattr: ("modul.ATRIBUT", hodnota) nebo (objekt, "jméno", hodnota).
    try:
        if value is notset and isinstance(target, str):
            module_name, _, attribute = target.rpartition(".")
            _record("monkeypatch", module_name, attribute, name)
        elif isinstance(name, str):
            owner = getattr(target, "__name__", None) or type(target).__qualname__
            _record("monkeypatch.object", str(owner), name, value)
    except Exception:  # pragma: no cover - audit nesmí ovlivnit běh testu
        pass
    return _original_setattr(self, target, name, value, raising=raising)


def pytest_configure(config: pytest.Config) -> None:
    mock._patch.__enter__ = _audited_enter  # type: ignore[attr-defined,method-assign]
    pytest.MonkeyPatch.setattr = _audited_setattr  # type: ignore[method-assign,assignment]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item):  # type: ignore[no-untyped-def]
    _CURRENT.update(test=_test_key(item.nodeid), phase="setup")
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item):  # type: ignore[no-untyped-def]
    _CURRENT.update(test=_test_key(item.nodeid), phase="call")
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: Any):  # type: ignore[no-untyped-def]
    _CURRENT.update(test=_test_key(item.nodeid), phase="teardown")
    try:
        return (yield)
    finally:
        for entry, replacement in _TRACKED:
            entry["called"] = bool(replacement.call_count) or bool(replacement.mock_calls)
            entry["callCount"] = int(replacement.call_count)
        _TRACKED.clear()
        _CURRENT.update(test=None, phase=None)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    out = os.environ.get("NC_MOCK_AUDIT_OUT")
    if not out:
        return
    Path(out).write_text(json.dumps(_RECORDS, indent=1, ensure_ascii=False), encoding="utf-8")
