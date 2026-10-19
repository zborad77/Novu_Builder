$ErrorActionPreference = "Stop"

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildDir = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$logDir = Join-Path $buildDir "automation-logs"
$vsDevCmd = "C:\Program Files\Microsoft Visual Studio\18\Professional\Common7\Tools\VsDevCmd.bat"
$cmakeExe = "C:\Qt\Tools\CMake_64\bin\cmake.exe"
$target = "NovuBuilder"
$timeoutSeconds = 900

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdoutLog = Join-Path $logDir "build-debug-$timestamp.stdout.log"
$stderrLog = Join-Path $logDir "build-debug-$timestamp.stderr.log"
$statusJson = Join-Path $logDir "build-debug-status.json"
$summaryTxt = Join-Path $logDir "build-debug-last.txt"

function Resolve-StaleBuildStatus {
    param(
        [string]$StatusJsonPath,
        [string]$SummaryTxtPath,
        [string]$BuildDirectory,
        [int]$StaleAfterMinutes
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

    $ageMinutes = ((Get-Date) - $startedAt).TotalMinutes
    if ($ageMinutes -lt $StaleAfterMinutes) {
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

    $payload = [ordered]@{
        status = "timeout"
        exit_code = 124
        message = "Previous build status was left in running state and was auto-resolved as timeout."
        timestamp = (Get-Date).ToString("s")
        build_dir = $BuildDirectory
        target = $existing.target
        stdout_log = $existing.stdout_log
        stderr_log = $existing.stderr_log
        exe = $existing.exe
    }

    $payload | ConvertTo-Json -Depth 5 | Set-Content -Path $StatusJsonPath -Encoding UTF8
    @(
        "status=timeout"
        "exit_code=124"
        "message=Previous build status was left in running state and was auto-resolved as timeout."
        "timestamp=$($payload.timestamp)"
        "stdout_log=$($existing.stdout_log)"
        "stderr_log=$($existing.stderr_log)"
    ) | Set-Content -Path $SummaryTxtPath -Encoding UTF8
}

function Write-BuildStatus {
    param(
        [string]$Status,
        [int]$ExitCode,
        [string]$Message
    )

    $exePath = Join-Path $buildDir "NovuBuilder.exe"
    $exeInfo = $null
    if (Test-Path $exePath) {
        $file = Get-Item $exePath
        $exeInfo = @{
            path = $file.FullName
            last_write_time = $file.LastWriteTime.ToString("s")
            length = $file.Length
        }
    }

    $payload = [ordered]@{
        status = $Status
        exit_code = $ExitCode
        message = $Message
        timestamp = (Get-Date).ToString("s")
        build_dir = $buildDir
        target = $target
        stdout_log = $stdoutLog
        stderr_log = $stderrLog
        exe = $exeInfo
    }

    $payload | ConvertTo-Json -Depth 5 | Set-Content -Path $statusJson -Encoding UTF8
    @(
        "status=$Status"
        "exit_code=$ExitCode"
        "message=$Message"
        "timestamp=$($payload.timestamp)"
        "stdout_log=$stdoutLog"
        "stderr_log=$stderrLog"
    ) | Set-Content -Path $summaryTxt -Encoding UTF8
}

Resolve-StaleBuildStatus -StatusJsonPath $statusJson -SummaryTxtPath $summaryTxt -BuildDirectory $buildDir -StaleAfterMinutes 5
Write-BuildStatus -Status "running" -ExitCode 0 -Message "Build started."

if (-not (Test-Path $vsDevCmd)) {
    Write-BuildStatus -Status "failed" -ExitCode 1 -Message "VS developer shell was not found: $vsDevCmd"
    throw "VS developer shell was not found: $vsDevCmd"
}

if (-not (Test-Path $cmakeExe)) {
    Write-BuildStatus -Status "failed" -ExitCode 1 -Message "CMake from Qt tools was not found: $cmakeExe"
    throw "CMake from Qt tools was not found: $cmakeExe"
}

if (-not (Test-Path (Join-Path $buildDir "build.ninja"))) {
    Write-BuildStatus -Status "failed" -ExitCode 1 -Message "Build directory is missing or not configured: $buildDir"
    throw "Build directory is missing or not configured: $buildDir"
}

$envDump = & cmd.exe /d /c "call `"$vsDevCmd`" -arch=amd64 >nul && set"
if ($LASTEXITCODE -ne 0) {
    Write-BuildStatus -Status "failed" -ExitCode $LASTEXITCODE -Message "Failed to initialize the Visual Studio developer environment."
    throw "Failed to initialize the Visual Studio developer environment."
}

foreach ($line in $envDump) {
    if ($line -match "^(.*?)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $cmakeExe
$psi.Arguments = "--build `"$buildDir`" --target $target"
$psi.WorkingDirectory = $projectDir
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi

$stdoutWriter = [System.IO.StreamWriter]::new($stdoutLog, $false, [System.Text.Encoding]::UTF8)
$stderrWriter = [System.IO.StreamWriter]::new($stderrLog, $false, [System.Text.Encoding]::UTF8)

try {
    if (-not $process.Start()) {
        Write-BuildStatus -Status "failed" -ExitCode 1 -Message "Build process could not be started."
        throw "Build process could not be started."
    }

    if (-not $process.WaitForExit($timeoutSeconds * 1000)) {
        try {
            $process.Kill($true)
        } catch {
        }
        $process.WaitForExit()
        $stdoutWriter.Write($process.StandardOutput.ReadToEnd())
        $stdoutWriter.Flush()
        $stderrWriter.Write($process.StandardError.ReadToEnd())
        $stderrWriter.Flush()
        Write-BuildStatus -Status "timeout" -ExitCode 124 -Message "Build timed out after $timeoutSeconds seconds."
        throw "Build timed out after $timeoutSeconds seconds."
    }

    $process.WaitForExit()
    $stdoutWriter.Write($process.StandardOutput.ReadToEnd())
    $stdoutWriter.Flush()
    $stderrWriter.Write($process.StandardError.ReadToEnd())
    $stderrWriter.Flush()
    $exitCode = $process.ExitCode
    if ($exitCode -eq 0) {
        Write-BuildStatus -Status "success" -ExitCode 0 -Message "Build completed successfully."
    } else {
        Write-BuildStatus -Status "failed" -ExitCode $exitCode -Message "Build failed."
    }

    exit $exitCode
}
finally {
    if ($null -ne $process) {
        $process.Dispose()
    }
    if ($null -ne $stdoutWriter) {
        $stdoutWriter.Dispose()
    }
    if ($null -ne $stderrWriter) {
        $stderrWriter.Dispose()
    }
}
