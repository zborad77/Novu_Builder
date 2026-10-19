@echo off
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
set "PATH=C:\Qt\6.10.3\msvc2022_64\bin;C:\Qt\Tools\CMake_64\bin;C:\Qt\Tools\Ninja;%PATH%"
cd /d "%~dp0build"
ninja -j4 NovuBuilder
echo BUILD_RESULT=%ERRORLEVEL%
endlocal
