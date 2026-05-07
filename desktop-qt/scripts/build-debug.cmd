@echo off
setlocal

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"

set "BUILD_DIR=%PROJECT_DIR%\build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
set "VSDEVCMD=C:\Program Files\Microsoft Visual Studio\18\Professional\Common7\Tools\VsDevCmd.bat"
set "CMAKE_EXE=C:\Qt\Tools\CMake_64\bin\cmake.exe"
set "TARGET=NovuBuilder"

if not exist "%VSDEVCMD%" (
    echo VS developer shell was not found:
    echo   %VSDEVCMD%
    exit /b 1
)

if not exist "%CMAKE_EXE%" (
    echo CMake from Qt tools was not found:
    echo   %CMAKE_EXE%
    exit /b 1
)

if not exist "%BUILD_DIR%\build.ninja" (
    echo Build directory is missing or not configured:
    echo   %BUILD_DIR%
    exit /b 1
)

call "%VSDEVCMD%" -arch=amd64 >nul
if errorlevel 1 (
    echo Failed to initialize the Visual Studio developer environment.
    exit /b 1
)

"%CMAKE_EXE%" --build "%BUILD_DIR%" --target "%TARGET%"
exit /b %errorlevel%
