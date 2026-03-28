"""Compatibility shim for `python -m uvicorn ... --reload` on Windows.

Uvicorn prefers the third-party `watchfiles` backend when it is installed.
With Python 3.14 on Windows, that backend currently crashes very early during
startup in local development on this project. By raising ImportError here,
Uvicorn falls back to its built-in StatReload implementation, so the standard
developer command keeps working from the `python-backend` directory.

Outside the affected platform/interpreter combination we proxy imports to the
real installed `watchfiles` package.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys


if sys.platform == "win32" and sys.version_info >= (3, 14):
    raise ImportError(
        "Local dev compatibility: force Uvicorn to use StatReload on "
        "Windows/Python 3.14."
    )


_REAL_SPEC = importlib.machinery.PathFinder.find_spec(__name__, sys.path[1:])
if _REAL_SPEC is None or _REAL_SPEC.loader is None:
    raise ImportError("watchfiles is not installed")

_REAL_MODULE = importlib.util.module_from_spec(_REAL_SPEC)
sys.modules[__name__] = _REAL_MODULE
_REAL_SPEC.loader.exec_module(_REAL_MODULE)

