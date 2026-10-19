@echo off
setlocal

cd /d "%~dp0src\backend"

:: Vytvor .env pokud neexistuje
if not exist ".env" (
    echo [INFO] Kopiruju .env.example -^> .env
    copy ".env.example" ".env" >nul
)

:: Vytvor virtualenv pokud neexistuje
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Vytvarim virtualenv...
    python -m venv .venv
)

:: Aktivuj virtualenv
call .venv\Scripts\activate.bat

:: Instaluj dependencies pokud chybi
python -c "import fastapi" 2>nul || (
    echo [INFO] Instaluji dependencies...
    pip install -r requirements.txt
)

echo.
echo ============================================================
echo  Backend: http://localhost:8000
echo  Swagger:  http://localhost:8000/docs
echo.
echo  Test ucty (seed data):
echo    superadmin : admin@novu.cz      / NovuAdmin2024!
echo    manager    : demo@novu.local    / demo1234
echo    technician : tech@novu.local    / tech1234
echo.
echo  POZOR: Redis musi bezet na localhost:6379
echo  Rychle spusteni Redisu:  docker run -d -p 6379:6379 redis:7-alpine
echo ============================================================
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

endlocal
