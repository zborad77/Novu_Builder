[CmdletBinding()]
param(
    [ValidateSet("sqlite", "postgres")]
    [string]$Target = "postgres",
    [string]$PostgresHost = "localhost",
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "novu_builder",
    [string]$PostgresUser = "novu",
    [string]$PostgresPassword = "novu",
    [switch]$RunMigrations,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendRoot = Join-Path $RepoRoot "python-backend"
$VenvPython = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$EnvExample = Join-Path $BackendRoot ".env.example"
$EnvFile = Join-Path $BackendRoot ".env"

function Write-Step {
    param([string]$Message)

    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail-WithHelp {
    param([string]$Message)

    throw ($Message + " Nejdriv spust: powershell -ExecutionPolicy Bypass -File scripts\bootstrap-dev.ps1")
}

function Ensure-BackendReady {
    if (-not (Test-Path $BackendRoot)) {
        throw "Chybi slozka python-backend v $RepoRoot"
    }

    if (-not (Test-Path $VenvPython)) {
        Fail-WithHelp "Backend virtualenv neni pripraveny."
    }

    if (-not (Test-Path $EnvFile)) {
        if (-not (Test-Path $EnvExample)) {
            throw "Chybi python-backend\\.env.example."
        }

        Copy-Item $EnvExample $EnvFile
    }
}

function Set-OrAppendEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Key,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $pattern = "^\s*" + [regex]::Escape($Key) + "\s*="
    for ($index = 0; $index -lt $script:envLines.Count; $index++) {
        if ($script:envLines[$index] -match $pattern) {
            $script:envLines[$index] = $Key + '="' + $Value + '"'
            return
        }
    }

    $script:envLines.Add($Key + '="' + $Value + '"')
}

function Test-PythonPackage {
    param([string]$ModuleName)

    & $VenvPython -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$ModuleName') else 1)"
    return $LASTEXITCODE -eq 0
}

function Ensure-PostgresDrivers {
    $missingPackages = @()

    if (-not (Test-PythonPackage -ModuleName "asyncpg")) {
        $missingPackages += "asyncpg"
    }

    if (-not (Test-PythonPackage -ModuleName "psycopg")) {
        $missingPackages += "psycopg[binary]"
    }

    if ($missingPackages.Count -eq 0) {
        return @{
            changed = $false
            missing = @()
        }
    }

    if ($DryRun) {
        return @{
            changed = $false
            missing = $missingPackages
        }
    }

    Write-Step "Instalace PostgreSQL driveru"
    & $VenvPython -m pip install --disable-pip-version-check @missingPackages
    if ($LASTEXITCODE -ne 0) {
        throw "Instalace PostgreSQL driveru selhala (exit code $LASTEXITCODE)"
    }

    return @{
        changed = $true
        missing = $missingPackages
    }
}

Ensure-BackendReady

$envLines = [System.Collections.Generic.List[string]]::new()
Get-Content $EnvFile | ForEach-Object { $envLines.Add($_) }

$driverInstall = @{
    changed = $false
    missing = @()
}

if ($Target -eq "sqlite") {
    Write-Step "Prepinam backend na SQLite"
    Set-OrAppendEnvValue -Key "DATABASE_URL" -Value "sqlite+aiosqlite:///./python-backend.db"
    Set-OrAppendEnvValue -Key "DATABASE_URL_SYNC" -Value "sqlite:///./python-backend.db"
    Set-OrAppendEnvValue -Key "DB_AUTO_CREATE_SCHEMA" -Value "true"
    Set-OrAppendEnvValue -Key "DB_SEED_ON_STARTUP" -Value "true"
} else {
    Write-Step "Prepinam backend na PostgreSQL"
    $driverInstall = Ensure-PostgresDrivers
    $postgresAsyncUrl = "postgresql+asyncpg://{0}:{1}@{2}:{3}/{4}" -f $PostgresUser, $PostgresPassword, $PostgresHost, $PostgresPort, $PostgresDatabase
    $postgresSyncUrl = "postgresql+psycopg://{0}:{1}@{2}:{3}/{4}" -f $PostgresUser, $PostgresPassword, $PostgresHost, $PostgresPort, $PostgresDatabase

    Set-OrAppendEnvValue -Key "DATABASE_URL" -Value $postgresAsyncUrl
    Set-OrAppendEnvValue -Key "DATABASE_URL_SYNC" -Value $postgresSyncUrl
    Set-OrAppendEnvValue -Key "DB_AUTO_CREATE_SCHEMA" -Value "false"
    Set-OrAppendEnvValue -Key "DB_SEED_ON_STARTUP" -Value "false"
}

if (-not $DryRun) {
    Set-Content -Path $EnvFile -Value $envLines -Encoding utf8
}

if ($RunMigrations) {
    if ($DryRun) {
        Write-Step "Dry run: migrace se pouze hlasi, nespousti"
    } else {
        Write-Step "Spoustim Alembic migrace"
        Push-Location $BackendRoot
        try {
            & $VenvPython -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) {
                throw "Alembic migrace selhaly (exit code $LASTEXITCODE)"
            }
        } finally {
            Pop-Location
        }
    }
}

$result = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    target = $Target
    dry_run = [bool]$DryRun
    env_file = $EnvFile
    database_url = ($envLines | Where-Object { $_ -match "^DATABASE_URL=" } | Select-Object -First 1)
    database_url_sync = ($envLines | Where-Object { $_ -match "^DATABASE_URL_SYNC=" } | Select-Object -First 1)
    db_auto_create_schema = ($envLines | Where-Object { $_ -match "^DB_AUTO_CREATE_SCHEMA=" } | Select-Object -First 1)
    db_seed_on_startup = ($envLines | Where-Object { $_ -match "^DB_SEED_ON_STARTUP=" } | Select-Object -First 1)
    postgres_driver_install = @{
        attempted = [bool]($Target -eq "postgres")
        changed = [bool]$driverInstall.changed
        missing_before_install = @($driverInstall.missing)
    }
    migrations_requested = [bool]$RunMigrations
    next_steps = if ($Target -eq "postgres") {
        @(
            "Over, ze PostgreSQL databaze existuje a prihlasovaci udaje v python-backend/.env sedi.",
            "Pokud jsi migrace nespustil ted, pust: cd python-backend; .\\.venv\\Scripts\\python.exe -m alembic upgrade head",
            "Pak backend spust pres powershell -ExecutionPolicy Bypass -File scripts\\start-dev.ps1"
        )
    } else {
        @(
            "SQLite rezim je pripraveny v python-backend/.env.",
            "Backend muzes spustit pres powershell -ExecutionPolicy Bypass -File scripts\\start-dev.ps1"
        )
    }
}

$result | ConvertTo-Json -Depth 5
