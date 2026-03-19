[CmdletBinding()]
param(
    [switch]$ImportReferenceCases
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $RepoRoot "python-backend"
$VenvPath = Join-Path $BackendRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\\python.exe"
$EnvExample = Join-Path $BackendRoot ".env.example"
$EnvFile = Join-Path $BackendRoot ".env"
$FilteredRequirements = Join-Path $BackendRoot ".requirements.bootstrap.txt"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Hint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Chybi prikaz '$Name'. $Hint"
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)"
    }
}

Write-Step "Kontrola zakladnich prikazu"
Ensure-Command -Name "python" -Hint "Nainstaluj Python 3.12+ a zkus to znovu."

Write-Step "Priprava Python virtualenv"
if (-not (Test-Path $VenvPython)) {
    Push-Location $BackendRoot
    try {
        python -m venv .venv
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtualenv se nepodarilo vytvorit v $VenvPath"
}

Write-Step "Instalace backend zavislosti"
$requirements = Get-Content (Join-Path $BackendRoot "requirements.txt") |
    Where-Object { $_.Trim() -and $_.Trim() -notin @("asyncpg", "psycopg[binary]") }
Set-Content -Path $FilteredRequirements -Value $requirements

Invoke-Checked `
    -FilePath $VenvPython `
    -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", $FilteredRequirements) `
    -FailureMessage "Instalace backend zavislosti selhala"

Write-Step "Kontrola .env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
}

Write-Step "Aplikace migraci"
Push-Location $BackendRoot
try {
    Invoke-Checked `
        -FilePath $VenvPython `
        -Arguments @("-m", "alembic", "upgrade", "head") `
        -FailureMessage "Alembic migrace selhaly"

    if ($ImportReferenceCases) {
        Write-Step "Import testovacich referenci"
        Invoke-Checked `
            -FilePath $VenvPython `
            -Arguments @("tools/import_reference_cases.py") `
            -FailureMessage "Import testovacich referenci selhal"
    }
} finally {
    if (Test-Path $FilteredRequirements) {
        Remove-Item $FilteredRequirements -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}

$result = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    repo_root = $RepoRoot
    backend_root = $BackendRoot
    python = $VenvPython
    env_file = @{
        path = $EnvFile
        exists = (Test-Path $EnvFile)
    }
    skipped_optional_packages = @(
        "asyncpg"
        "psycopg[binary]"
    )
    reference_cases_imported = [bool]$ImportReferenceCases
    next_steps = @(
        "Spust backend: cd python-backend; .venv\\Scripts\\activate; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload",
        "Pro desktop zkontroluj Qt 6 + MSVC kit v Qt Creatoru",
        "Potom muzes pustit scripts\\setup-check.ps1 a desktop-qt\\scripts\\smoke-check.ps1",
        "Pokud budes chtit PostgreSQL rezim, doinstaluj pozdeji i asyncpg a psycopg[binary]"
    )
}

Write-Host ""
$result | ConvertTo-Json -Depth 5
