@echo off
setlocal EnableExtensions

:: ============================================================
::  Novu Builder - kanonicky build/validacni skript projektu
::
::  Pouziti:
::    build.bat            backend + frontend (vychozi)
::    build.bat backend    jen backend (compileall, ruff, mypy, lint-imports)
::    build.bat frontend   jen frontend (npm run build = tsc -b + vite build)
::    build.bat desktop    jen desktop (deleguje na src\desktop\build.bat)
::    build.bat all        backend + frontend + desktop
::
::  Skript nic neinstaluje ani nekonfiguruje: ocekava pripraveny
::  src\backend\.venv a src\frontend\node_modules (viz scripts\bootstrap-dev.ps1).
::  Navratovy kod je nenulovy, pokud selze kterykoli krok.
:: ============================================================

set "ROOT=%~dp0"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=default"

set "DO_BACKEND=0"
set "DO_FRONTEND=0"
set "DO_DESKTOP=0"
if /i "%TARGET%"=="default"  (set "DO_BACKEND=1" & set "DO_FRONTEND=1")
if /i "%TARGET%"=="backend"  set "DO_BACKEND=1"
if /i "%TARGET%"=="frontend" set "DO_FRONTEND=1"
if /i "%TARGET%"=="desktop"  set "DO_DESKTOP=1"
if /i "%TARGET%"=="all"      (set "DO_BACKEND=1" & set "DO_FRONTEND=1" & set "DO_DESKTOP=1")
if "%DO_BACKEND%%DO_FRONTEND%%DO_DESKTOP%"=="000" (
    echo [error] Neznamy cil "%TARGET%". Pouzij: backend ^| frontend ^| desktop ^| all
    exit /b 2
)

if "%DO_BACKEND%"=="1" call :backend || exit /b 1
if "%DO_FRONTEND%"=="1" call :frontend || exit /b 1
if "%DO_DESKTOP%"=="1" call :desktop || exit /b 1

echo.
echo [build] OK (%TARGET%)
endlocal
exit /b 0

:: ------------------------------------------------------------
:backend
echo.
echo === [backend] src\backend ===
set "VENV=%ROOT%src\backend\.venv\Scripts"
if not exist "%VENV%\python.exe" (
    echo [error] Chybi src\backend\.venv - spust scripts\bootstrap-dev.ps1
    exit /b 1
)
pushd "%ROOT%src\backend"
echo [backend] compileall app
"%VENV%\python.exe" -m compileall -q app || goto :backend_fail
echo [backend] ruff check app/
"%VENV%\python.exe" -m ruff check app/ || goto :backend_fail
echo [backend] mypy app/
"%VENV%\python.exe" -m mypy app/ || goto :backend_fail
echo [backend] lint-imports
"%VENV%\lint-imports.exe" || goto :backend_fail
popd
echo [backend] OK
exit /b 0
:backend_fail
popd
echo [error] Backend validace selhala.
exit /b 1

:: ------------------------------------------------------------
:frontend
echo.
echo === [frontend] src\frontend ===
if not exist "%ROOT%src\frontend\node_modules" (
    echo [error] Chybi src\frontend\node_modules - spust "npm ci" v src\frontend
    exit /b 1
)
pushd "%ROOT%src\frontend"
call npm run build
if errorlevel 1 (
    popd
    echo [error] Frontend build selhal.
    exit /b 1
)
popd
echo [frontend] OK
exit /b 0

:: ------------------------------------------------------------
:desktop
echo.
echo === [desktop] src\desktop ===
call "%ROOT%src\desktop\build.bat"
if errorlevel 1 (
    echo [error] Desktop build selhal.
    exit /b 1
)
echo [desktop] OK
exit /b 0
