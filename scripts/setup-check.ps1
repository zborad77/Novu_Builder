[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Get-CommandInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        return @{
            status = "missing"
            details = $null
        }
    }

    return @{
        status = "ok"
        details = $command.Source
    }
}

function Get-VersionOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandLine
    )

    try {
        return (Invoke-Expression $CommandLine 2>$null | Select-Object -First 1)
    } catch {
        return $null
    }
}

$checks = [ordered]@{}

$checks.git = Get-CommandInfo -Name "git"
$checks.python = Get-CommandInfo -Name "python"
$checks.cmake = Get-CommandInfo -Name "cmake"

$qtpaths = Get-CommandInfo -Name "qtpaths"
$qmake = Get-CommandInfo -Name "qmake"
if ($qtpaths.status -eq "ok") {
    $checks.qt = @{
        status = "ok"
        details = "qtpaths: $($qtpaths.details)"
    }
} elseif ($qmake.status -eq "ok") {
    $checks.qt = @{
        status = "ok"
        details = "qmake: $($qmake.details)"
    }
} else {
    $checks.qt = @{
        status = "missing"
        details = $null
    }
}

$checks.msvc_shell = @{
    status = if ($env:VSCMD_VER -or $env:VCINSTALLDIR) { "ok" } else { "not_in_shell" }
    details = if ($env:VSCMD_VER) { "VSCMD_VER=$($env:VSCMD_VER)" } elseif ($env:VCINSTALLDIR) { "VCINSTALLDIR=$($env:VCINSTALLDIR)" } else { "MSVC shell not active in current session." }
}

$checks.git.version = Get-VersionOutput -CommandLine "git --version"
$checks.python.version = Get-VersionOutput -CommandLine "python --version"
$checks.cmake.version = Get-VersionOutput -CommandLine "cmake --version"

$overallStatus = "ok"
foreach ($entry in $checks.GetEnumerator()) {
    if ($entry.Value.status -eq "missing") {
        $overallStatus = "needs_setup"
        break
    }
}

$result = [ordered]@{
    timestamp = (Get-Date).ToString("s")
    overall_status = $overallStatus
    checks = $checks
}

$result | ConvertTo-Json -Depth 5
