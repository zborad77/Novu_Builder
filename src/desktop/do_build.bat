@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
set "PATH=C:\Qt\6.10.3\msvc2022_64\bin;C:\Qt\Tools\CMake_64\bin;C:\Qt\Tools\Ninja;%PATH%"

echo [build] Incrementalni build...
cd /d "%~dp0build"
ninja -j4 NovuBuilder 2>&1
echo EXIT_CODE=%ERRORLEVEL%
