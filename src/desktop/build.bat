@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ============================================
echo  Novu Builder Desktop - Full Build
echo ============================================
echo.

set "ROOT=%~dp0"
set "BUILD_DIR=%ROOT%build"
set "QT_DIR=C:\Qt\6.10.3\msvc2022_64"
set "QT_TOOLS=C:\Qt\Tools"
set "CMAKE_BIN=%QT_TOOLS%\CMake_64\bin\cmake.exe"
set "NINJA_BIN=%QT_TOOLS%\Ninja\ninja.exe"
set "WINDEPLOYQT=%QT_DIR%\bin\windeployqt.exe"

for /f "tokens=2 delims=:" %%a in ('findstr "version" "%ROOT%version.json"') do (
    set "VER=%%~a"
    set "VER=!VER: =!"
    set "VER=!VER:"=!"
    set "VER=!VER:,=!"
)
echo [version] !VER!
echo.

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
if errorlevel 1 (
    echo [error] Failed to initialize MSVC build environment.
    exit /b 1
)

set "PATH=%QT_DIR%\bin;%QT_TOOLS%\CMake_64\bin;%QT_TOOLS%\Ninja;%PATH%"

echo [build] Konfiguruji CMake...
"%CMAKE_BIN%" -B "%BUILD_DIR%" -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_PREFIX_PATH="%QT_DIR%" -S "%ROOT%"
if errorlevel 1 (
    echo [error] CMake konfigurace selhala!
    exit /b 1
)
echo.

echo [build] Kompiluji...
"%CMAKE_BIN%" --build "%BUILD_DIR%" --target NovuBuilder
if errorlevel 1 (
    echo [error] Build selhal!
    exit /b 1
)
echo.

echo [deploy] Kopíruji Qt DLL...
"%WINDEPLOYQT%" "%BUILD_DIR%\NovuBuilder.exe"
if errorlevel 1 (
    echo [warning] windeployqt hlasil problemy, pokracuji...
)
echo.

echo ============================================
echo  Hotovo! Spust: %BUILD_DIR%\NovuBuilder.exe
echo ============================================
endlocal
