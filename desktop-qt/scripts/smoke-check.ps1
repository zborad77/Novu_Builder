$ErrorActionPreference = "Stop"

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildDir = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$logDir = Join-Path $buildDir "automation-logs"
$statusJson = Join-Path $logDir "build-debug-status.json"
$reportJson = Join-Path $logDir "smoke-check-status.json"
$backendHealthUrl = "http://127.0.0.1:8000/api/v1/health"
$exePath = Join-Path $buildDir "FotoNabidkaDesktop.exe"

function Resolve-StaleBuildStatus {
    param(
        [string]$StatusJsonPath,
        [string]$BuildDirectory
    )

    if (-not (Test-Path $StatusJsonPath)) {
        return
    }

    try {
        $existing = Get-Content -Path $StatusJsonPath -Raw | ConvertFrom-Json
    } catch {
        return
    }

    if ($existing.status -ne "running") {
        return
    }

    $startedAt = $null
    try {
        $startedAt = [datetime]::Parse($existing.timestamp)
    } catch {
        return
    }

    if (((Get-Date) - $startedAt).TotalMinutes -lt 5) {
        return
    }

    $buildDirPattern = [Regex]::Escape($BuildDirectory)
    $activeBuildProcess = $null
    try {
        $activeBuildProcess = Get-CimInstance Win32_Process -Filter "Name = 'cmake.exe'" |
            Where-Object { $_.CommandLine -match $buildDirPattern } |
            Select-Object -First 1
    } catch {
        $activeBuildProcess = $null
    }

    if ($null -ne $activeBuildProcess) {
        return
    }

    $existing.status = "timeout"
    $existing.exit_code = 124
    $existing.message = "Build status was auto-resolved from stale running to timeout."
    $existing.timestamp = (Get-Date).ToString("s")
    $existing | ConvertTo-Json -Depth 6 | Set-Content -Path $StatusJsonPath -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Resolve-StaleBuildStatus -StatusJsonPath $statusJson -BuildDirectory $buildDir

$result = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    checks = [ordered]@{
        backend_health = [ordered]@{
            status = "unknown"
            details = $null
        }
        desktop_exe = [ordered]@{
            status = "unknown"
            details = $null
        }
        build_status = [ordered]@{
            status = "unknown"
            details = $null
        }
    }
}

try {
    $health = Invoke-RestMethod -Uri $backendHealthUrl -Method Get -TimeoutSec 5
    $result.checks.backend_health.status = "success"
    $result.checks.backend_health.details = $health
} catch {
    $result.checks.backend_health.status = "failed"
    $result.checks.backend_health.details = $_.Exception.Message
}

if (Test-Path $exePath) {
    $exe = Get-Item $exePath
    $result.checks.desktop_exe.status = "success"
    $result.checks.desktop_exe.details = @{
        path = $exe.FullName
        last_write_time = $exe.LastWriteTime.ToString("s")
        length = $exe.Length
    }
} else {
    $result.checks.desktop_exe.status = "failed"
    $result.checks.desktop_exe.details = "Desktop executable was not found."
}

if (Test-Path $statusJson) {
    try {
        $buildStatus = Get-Content -Path $statusJson -Raw | ConvertFrom-Json
        $result.checks.build_status.status = $buildStatus.status
        $result.checks.build_status.details = $buildStatus
    } catch {
        $result.checks.build_status.status = "failed"
        $result.checks.build_status.details = "Build status file exists but could not be parsed."
    }
} else {
    $result.checks.build_status.status = "missing"
    $result.checks.build_status.details = "Build status file does not exist yet."
}

$result | ConvertTo-Json -Depth 6 | Set-Content -Path $reportJson -Encoding UTF8
$result | ConvertTo-Json -Depth 6
