@echo off
setlocal

cd /d "%~dp0src\frontend"

:: Vytvor .env.local pokud neexistuje (URL backendu)
if not exist ".env.local" (
    echo [INFO] Vytvarim .env.local s URL backendu...
    echo VITE_API_BASE_URL=http://localhost:8000/api/v1>.env.local
)

:: Instaluj node_modules pokud chybi
if not exist "node_modules" (
    echo [INFO] Instaluji npm dependencies...
    npm install
)

echo.
echo ============================================================
echo  Web frontend: http://localhost:5173
echo  Backend musi bezet na: http://localhost:8000
echo  (spust backend.bat v jinem terminalu)
echo ============================================================
echo.

npm run dev

endlocal
