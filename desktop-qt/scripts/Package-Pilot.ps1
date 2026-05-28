#Requires -Version 5.1
# Package NovuBuilder.exe with all Qt runtime dependencies for pilot distribution.
# Runs windeployqt on the Debug build and copies everything to dist\NovuBuilder-pilot\.
#
# Usage:
#   .\desktop-qt\scripts\Package-Pilot.ps1

$ErrorActionPreference = "Stop"

$projectDir  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildDir    = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$exePath     = Join-Path $buildDir "NovuBuilder.exe"
$distDir     = Join-Path $projectDir "dist\NovuBuilder-pilot"
$winDeployQt = "C:\Qt\6.10.2\msvc2022_64\bin\windeployqt.exe"

if (-not (Test-Path $exePath)) {
    Write-Error "NovuBuilder.exe not found at: $exePath`nRun build-debug.ps1 first."
    exit 1
}

if (-not (Test-Path $winDeployQt)) {
    Write-Error "windeployqt not found at: $winDeployQt`nAdjust the path if your Qt installation differs."
    exit 1
}

if (Test-Path $distDir) {
    Remove-Item $distDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

Write-Host "Copying NovuBuilder.exe -> $distDir"
Copy-Item $exePath $distDir

Write-Host "Running windeployqt..."
& $winDeployQt --dir $distDir (Join-Path $distDir "NovuBuilder.exe")
if ($LASTEXITCODE -ne 0) {
    Write-Error "windeployqt failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$size = (Get-ChildItem $distDir -Recurse | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($size / 1MB, 1)

Write-Host ""
Write-Host "Package ready: $distDir  ($sizeMB MB, $((Get-ChildItem $distDir -Recurse -File).Count) files)"
Write-Host ""
Write-Host "To run on the target machine:"
Write-Host "  1. Copy the entire '$distDir' folder to the target PC"
Write-Host "  2. Run Trust-PilotCert.ps1 OR install cert.pem in Windows cert manager"
Write-Host "  3. Start NovuBuilder.exe -> set server URL -> log in"
