$ErrorActionPreference = "Stop"

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectDir "..")).Path
$backendDir = Join-Path $repoRoot "python-backend"
$buildDir = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$logDir = Join-Path $buildDir "automation-logs"
$statusJson = Join-Path $logDir "smoke-workflow-status.json"
$summaryTxt = Join-Path $logDir "smoke-workflow-last.txt"
$backendHealthUrl = "http://127.0.0.1:8000/api/v1/health"
$casesUrl = "http://127.0.0.1:8000/api/v1/cases"
$cleanupScript = Join-Path $backendDir "tools\delete_project.py"

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
    source_images = [ordered]@{ status = "pending"; details = $null }
    duplicate_case = [ordered]@{ status = "pending"; details = $null }
    duplicate_images = [ordered]@{ status = "pending"; details = $null }
    cleanup = [ordered]@{ status = "pending"; details = $null }
}

Write-SmokeStatus -Status "running" -Message "Smoke workflow started." -Checks $checks

$duplicateCaseId = $null

try {
    try {
        $health = Invoke-RestMethod -Uri $backendHealthUrl -Method Get -TimeoutSec 5
        $checks.backend_health.status = "success"
        $checks.backend_health.details = $health
    } catch {
        $checks.backend_health.status = "failed"
        $checks.backend_health.details = $_.Exception.Message
        throw "Backend health check failed."
    }

    $caseList = Invoke-RestMethod -Uri $casesUrl -Method Get -TimeoutSec 10
    $sourceCase = $caseList.items | Where-Object { $_.isReferenceDataset -and $_.photoCount -gt 0 } | Select-Object -First 1
    if ($null -eq $sourceCase) {
        $checks.source_case.status = "failed"
        $checks.source_case.details = "No reference dataset case with photos was found."
        throw "No reference dataset case with photos was found."
    }

    $checks.source_case.status = "success"
    $checks.source_case.details = @{
        id = $sourceCase.id
        title = $sourceCase.title
        photoCount = $sourceCase.photoCount
    }

    $sourceImagesResponse = Invoke-RestMethod -Uri "$casesUrl/$($sourceCase.id)/images" -Method Get -TimeoutSec 10
    $sourceImages = @($sourceImagesResponse.items)
    if ($sourceImages.Count -lt 1) {
        $checks.source_images.status = "failed"
        $checks.source_images.details = "Source case has no images."
        throw "Source case has no images."
    }

    $sourcePrimary = $sourceImages | Where-Object { $_.isPrimary } | Select-Object -First 1
    $sourceAnalysisReference = $sourceImages | Where-Object { $_.isAnalysisReference } | Select-Object -First 1
    $checks.source_images.status = "success"
    $checks.source_images.details = @{
        count = $sourceImages.Count
        primaryPhotoId = $sourceImagesResponse.meta.primaryPhotoId
        analysisReferencePhotoId = $sourceImagesResponse.meta.analysisReferencePhotoId
        primaryFilename = if ($null -ne $sourcePrimary) { $sourcePrimary.originalFilename } else { $null }
        analysisReferenceFilename = if ($null -ne $sourceAnalysisReference) { $sourceAnalysisReference.originalFilename } else { $null }
    }

    $duplicatePayload = @{ mode = "copy" } | ConvertTo-Json
    $duplicateResponse = Invoke-RestMethod -Uri "$casesUrl/$($sourceCase.id)/duplicate" -Method Post -ContentType "application/json" -Body $duplicatePayload -TimeoutSec 15
    $duplicateCaseId = $duplicateResponse.id
    if ([string]::IsNullOrWhiteSpace($duplicateCaseId)) {
        $checks.duplicate_case.status = "failed"
        $checks.duplicate_case.details = "Duplicate endpoint returned no project id."
        throw "Duplicate endpoint returned no project id."
    }

    $duplicateDetail = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId" -Method Get -TimeoutSec 10
    $checks.duplicate_case.status = "success"
    $checks.duplicate_case.details = @{
        id = $duplicateCaseId
        title = $duplicateDetail.title
        status = $duplicateDetail.status
        sourceId = $sourceCase.id
    }

    $duplicateImagesResponse = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/images" -Method Get -TimeoutSec 10
    $duplicateImages = @($duplicateImagesResponse.items)
    $duplicatePrimary = $duplicateImages | Where-Object { $_.isPrimary } | Select-Object -First 1
    $duplicateAnalysisReference = $duplicateImages | Where-Object { $_.isAnalysisReference } | Select-Object -First 1

    $titleOk = ($duplicateDetail.title -eq "$($sourceCase.title) - Kopie")
    $countOk = ($duplicateImages.Count -eq $sourceImages.Count)
    $primaryOk = ($null -ne $duplicatePrimary)
    $analysisOk = ($null -ne $duplicateAnalysisReference)

    if (-not ($titleOk -and $countOk -and $primaryOk -and $analysisOk)) {
        $checks.duplicate_images.status = "failed"
        $checks.duplicate_images.details = @{
            count = $duplicateImages.Count
            expectedCount = $sourceImages.Count
            title = $duplicateDetail.title
            expectedTitle = "$($sourceCase.title) - Kopie"
            primaryFilename = if ($null -ne $duplicatePrimary) { $duplicatePrimary.originalFilename } else { $null }
            analysisReferenceFilename = if ($null -ne $duplicateAnalysisReference) { $duplicateAnalysisReference.originalFilename } else { $null }
        }
        throw "Duplicate workflow validation failed."
    }

    $checks.duplicate_images.status = "success"
    $checks.duplicate_images.details = @{
        count = $duplicateImages.Count
        expectedCount = $sourceImages.Count
        primaryFilename = $duplicatePrimary.originalFilename
        analysisReferenceFilename = $duplicateAnalysisReference.originalFilename
        primaryPhotoId = $duplicateImagesResponse.meta.primaryPhotoId
        analysisReferencePhotoId = $duplicateImagesResponse.meta.analysisReferencePhotoId
    }

    if (-not (Test-Path $cleanupScript)) {
        $checks.cleanup.status = "failed"
        $checks.cleanup.details = "Cleanup helper was not found."
        throw "Cleanup helper was not found."
    }

    & python $cleanupScript --project-id $duplicateCaseId --allow-prefix prj_
    if ($LASTEXITCODE -ne 0) {
        $checks.cleanup.status = "failed"
        $checks.cleanup.details = "Cleanup helper failed with exit code $LASTEXITCODE."
        throw "Cleanup helper failed with exit code $LASTEXITCODE."
    }

    $checks.cleanup.status = "success"
    $checks.cleanup.details = @{
        deletedProjectId = $duplicateCaseId
    }

    Write-SmokeStatus -Status "success" -Message "Smoke workflow passed." -Checks $checks
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
