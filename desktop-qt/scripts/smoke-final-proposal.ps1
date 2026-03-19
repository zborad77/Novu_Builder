$ErrorActionPreference = "Stop"

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectDir "..")).Path
$backendDir = Join-Path $repoRoot "python-backend"
$buildDir = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$logDir = Join-Path $buildDir "automation-logs"
$statusJson = Join-Path $logDir "smoke-final-proposal-status.json"
$summaryTxt = Join-Path $logDir "smoke-final-proposal-last.txt"
$backendHealthUrl = "http://127.0.0.1:8000/api/v1/health"
$casesUrl = "http://127.0.0.1:8000/api/v1/cases"
$cleanupScript = Join-Path $backendDir "tools\delete_project.py"
$storageExportsRoot = Join-Path $repoRoot "storage\exports"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-SmokeStatus {
    param(
        [string]$Status,
        [string]$Message,
        [hashtable]$Checks
    )

    $payload = [ordered]@{
        status = $Status
        message = $Message
        timestamp = (Get-Date).ToString("s")
        checks = $Checks
    }

    $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $statusJson -Encoding UTF8
    @(
        "status=$Status"
        "message=$Message"
        "timestamp=$($payload.timestamp)"
    ) | Set-Content -Path $summaryTxt -Encoding UTF8
}

$checks = [ordered]@{
    backend_health = [ordered]@{ status = "pending"; details = $null }
    source_case = [ordered]@{ status = "pending"; details = $null }
    duplicate_case = [ordered]@{ status = "pending"; details = $null }
    final_proposal = [ordered]@{ status = "pending"; details = $null }
    exports = [ordered]@{ status = "pending"; details = $null }
    cleanup = [ordered]@{ status = "pending"; details = $null }
}

Write-SmokeStatus -Status "running" -Message "Final proposal smoke workflow started." -Checks $checks

$duplicateCaseId = $null

try {
    $health = Invoke-RestMethod -Uri $backendHealthUrl -Method Get -TimeoutSec 5
    if (-not $health.ready) {
        $checks.backend_health.status = "failed"
        $checks.backend_health.details = $health
        throw "Backend startup checks are not ready."
    }
    $checks.backend_health.status = "success"
    $checks.backend_health.details = $health

    $caseList = Invoke-RestMethod -Uri $casesUrl -Method Get -TimeoutSec 10
    $sourceCase = $caseList.items | Where-Object { $_.isReferenceDataset -and $_.photoCount -ge 3 } | Select-Object -First 1
    if ($null -eq $sourceCase) {
        $checks.source_case.status = "failed"
        $checks.source_case.details = "No reference dataset case with at least 3 photos was found."
        throw "No reference dataset case with at least 3 photos was found."
    }
    $checks.source_case.status = "success"
    $checks.source_case.details = @{
        id = $sourceCase.id
        title = $sourceCase.title
        photoCount = $sourceCase.photoCount
    }

    $duplicatePayload = @{ mode = "copy" } | ConvertTo-Json
    $duplicateResponse = Invoke-RestMethod -Uri "$casesUrl/$($sourceCase.id)/duplicate" -Method Post -ContentType "application/json" -Body $duplicatePayload -TimeoutSec 15
    $duplicateCaseId = $duplicateResponse.id
    if ([string]::IsNullOrWhiteSpace($duplicateCaseId)) {
        throw "Duplicate endpoint returned no project id."
    }
    $checks.duplicate_case.status = "success"
    $checks.duplicate_case.details = @{
        id = $duplicateCaseId
        sourceId = $sourceCase.id
    }

    $finalDetail = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/final-proposal" -Method Post -TimeoutSec 20
    if ($null -eq $finalDetail.finalProposal) {
        $checks.final_proposal.status = "failed"
        $checks.final_proposal.details = "Final proposal payload is missing."
        throw "Final proposal payload is missing."
    }
    $checks.final_proposal.status = "success"
    $checks.final_proposal.details = @{
        id = $finalDetail.finalProposal.id
        status = $finalDetail.finalProposal.status
        draftVersion = $finalDetail.finalProposal.draftVersion
    }

    $exportDir = Join-Path $storageExportsRoot $duplicateCaseId
    $docxFiles = @()
    $pdfFiles = @()
    if (Test-Path $exportDir) {
        $docxFiles = @(Get-ChildItem -Path $exportDir -Filter *.docx -File)
        $pdfFiles = @(Get-ChildItem -Path $exportDir -Filter *.pdf -File)
    }

    if ($docxFiles.Count -lt 1 -or $pdfFiles.Count -lt 1) {
        $checks.exports.status = "failed"
        $checks.exports.details = @{
            exportDir = $exportDir
            docxCount = $docxFiles.Count
            pdfCount = $pdfFiles.Count
        }
        throw "Final proposal exports were not generated."
    }

    $checks.exports.status = "success"
    $checks.exports.details = @{
        exportDir = $exportDir
        docxCount = $docxFiles.Count
        pdfCount = $pdfFiles.Count
        docxNames = @($docxFiles | ForEach-Object { $_.Name })
        pdfNames = @($pdfFiles | ForEach-Object { $_.Name })
    }

    & python $cleanupScript --project-id $duplicateCaseId --allow-prefix prj_
    if ($LASTEXITCODE -ne 0) {
        throw "Cleanup helper failed with exit code $LASTEXITCODE."
    }
    $checks.cleanup.status = "success"
    $checks.cleanup.details = @{
        deletedProjectId = $duplicateCaseId
    }

    Write-SmokeStatus -Status "success" -Message "Final proposal smoke workflow passed." -Checks $checks
    $checks | ConvertTo-Json -Depth 8
    exit 0
}
catch {
    if ($duplicateCaseId -and $checks.cleanup.status -eq "pending" -and (Test-Path $cleanupScript)) {
        try {
            & python $cleanupScript --project-id $duplicateCaseId --allow-prefix prj_ | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $checks.cleanup.status = "success"
                $checks.cleanup.details = @{
                    deletedProjectId = $duplicateCaseId
                    triggeredFromErrorPath = $true
                }
            } else {
                $checks.cleanup.status = "failed"
                $checks.cleanup.details = "Cleanup helper failed during error handling with exit code $LASTEXITCODE."
            }
        } catch {
            $checks.cleanup.status = "failed"
            $checks.cleanup.details = $_.Exception.Message
        }
    } elseif ($checks.cleanup.status -eq "pending") {
        $checks.cleanup.status = "skipped"
        $checks.cleanup.details = "No duplicate project needed cleanup."
    }

    Write-SmokeStatus -Status "failed" -Message $_.Exception.Message -Checks $checks
    $checks | ConvertTo-Json -Depth 8
    exit 1
}
