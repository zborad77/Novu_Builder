[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $RepoRoot "python-backend"
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$EnvFile = Join-Path $BackendRoot ".env"

function Fail-WithHelp {
    param([string]$Message)

    throw ($Message + " Nejdriv spust: powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1")
}

if (-not (Test-Path $BackendRoot)) {
    throw "Chybi slozka python-backend v $RepoRoot"
}

if (-not (Test-Path $VenvPython)) {
    Fail-WithHelp "Backend virtualenv neni pripraveny."
}

if (-not (Test-Path $EnvFile)) {
    Fail-WithHelp "Chybi python-backend\\.env."
}

$backendCommand = "Set-Location '$BackendRoot'; & '$VenvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

$result = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    repo_root = $RepoRoot
    backend_root = $BackendRoot
    backend_python = $VenvPython
    env_file = $EnvFile
    command = $backendCommand
    mode = if ($DryRun) { "dry_run" } else { "start_backend" }
    next_steps = @(
        "Pockej na hlasku 'Application startup complete.'",
        "Potom muzes pustit desktop-qt\\scripts\\smoke-check.ps1",
        "A v Qt Creatoru otevrit desktop-qt/CMakeLists.txt"
    )
}

if (-not $DryRun) {
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $backendCommand
    ) | Out-Null
}

$result | ConvertTo-Json -Depth 4
