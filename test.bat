@echo off
setlocal EnableExtensions

:: ============================================================
::  Novu Builder - kanonicky testovaci skript projektu
::
::  Pouziti:
::    test.bat             backend + frontend (vychozi)
::    test.bat backend     pytest + kontrola kontraktu (export_contracts --check)
::    test.bat frontend    check:contracts + lint (ESLint)
::    test.bat pytest ...  jen pytest; dalsi argumenty jdou primo pytestu
::                         (napr. test.bat pytest tests\test_d1_e2e_analysis_flow.py -v)
::
::  Skript nic neinstaluje ani nekonfiguruje: ocekava pripraveny
::  src\backend\.venv a src\frontend\node_modules (viz scripts\bootstrap-dev.ps1).
::  Pytest bezi proti docasne SQLite DB (conftest), pokud neni nastaven TEST_DATABASE_URL.
::  Navratovy kod je nenulovy, pokud selze kterykoli krok.
:: ============================================================

set "ROOT=%~dp0"
set "VENV=%ROOT%src\backend\.venv\Scripts"
set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=default"

if /i "%TARGET%"=="pytest" goto :pytest_only

set "DO_BACKEND=0"
set "DO_FRONTEND=0"
if /i "%TARGET%"=="default"  (set "DO_BACKEND=1" & set "DO_FRONTEND=1")
if /i "%TARGET%"=="backend"  set "DO_BACKEND=1"
if /i "%TARGET%"=="frontend" set "DO_FRONTEND=1"
if "%DO_BACKEND%%DO_FRONTEND%"=="00" (
    echo [error] Neznamy cil "%TARGET%". Pouzij: backend ^| frontend ^| pytest [args]
    exit /b 2
)

if "%DO_BACKEND%"=="1" call :backend || exit /b 1
if "%DO_FRONTEND%"=="1" call :frontend || exit /b 1

echo.
echo [test] OK (%TARGET%)
endlocal
exit /b 0

:: ------------------------------------------------------------
:pytest_only
call :require_venv || exit /b 1
shift
set "ARGS="
:collect_args
if "%~1"=="" goto :run_pytest_only
set ARGS=%ARGS% %1
shift
goto :collect_args
:run_pytest_only
if "%ARGS%"=="" set "ARGS= tests/"
pushd "%ROOT%src\backend"
"%VENV%\python.exe" -m pytest%ARGS%
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:: ------------------------------------------------------------
:require_venv
if not exist "%VENV%\python.exe" (
    echo [error] Chybi src\backend\.venv - spust scripts\bootstrap-dev.ps1
    exit /b 1
)
exit /b 0

:: ------------------------------------------------------------
:backend
echo.
echo === [backend] src\backend ===
call :require_venv || exit /b 1
pushd "%ROOT%src\backend"
echo [backend] pytest tests/
"%VENV%\python.exe" -m pytest tests/ -q || goto :backend_fail
echo [backend] export_contracts --check
"%VENV%\python.exe" -m scripts.export_contracts --check || goto :backend_fail
popd
echo [backend] OK
exit /b 0
:backend_fail
popd
echo [error] Backend testy selhaly.
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
call npm run check:contracts
if errorlevel 1 goto :frontend_fail
call npm run lint
if errorlevel 1 goto :frontend_fail
popd
echo [frontend] OK
exit /b 0
:frontend_fail
popd
echo [error] Frontend kontroly selhaly.
exit /b 1
