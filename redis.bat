@echo off
echo Spoustim Redis pres Docker...
echo (Redis je vyzadovan backendem pro AI joby a session management)
echo.
docker run -d --name novu-redis -p 6379:6379 redis:7-alpine
if %errorlevel% equ 0 (
    echo [OK] Redis bezi na localhost:6379
) else (
    echo [INFO] Zkousim znovu spustit existujici kontejner...
    docker start novu-redis
)
echo.
pause
