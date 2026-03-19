$ErrorActionPreference = "Stop"

$projectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectDir "..")).Path
$backendDir = Join-Path $repoRoot "python-backend"
$buildDir = Join-Path $projectDir "build\Desktop_Qt_6_10_2_MSVC2022_64bit-Debug"
$logDir = Join-Path $buildDir "automation-logs"
$statusJson = Join-Path $logDir "smoke-draft-send-guard-status.json"
$summaryTxt = Join-Path $logDir "smoke-draft-send-guard-last.txt"
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
    duplicate_case = [ordered]@{ status = "pending"; details = $null }
    send_guard = [ordered]@{ status = "pending"; details = $null }
    draft_patch = [ordered]@{ status = "pending"; details = $null }
    final_proposal = [ordered]@{ status = "pending"; details = $null }
    send_after_final = [ordered]@{ status = "pending"; details = $null }
    cleanup = [ordered]@{ status = "pending"; details = $null }
}

Write-SmokeStatus -Status "running" -Message "Draft patch / send guard smoke workflow started." -Checks $checks

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
        throw "No reference dataset case with at least 3 photos was found."
    }
    $checks.source_case.status = "success"
    $checks.source_case.details = @{
        id = $sourceCase.id
        title = $sourceCase.title
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

    try {
        Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/send" -Method Post -TimeoutSec 10 | Out-Null
        $checks.send_guard.status = "failed"
        $checks.send_guard.details = "Send unexpectedly passed before final proposal existed."
        throw "Send unexpectedly passed before final proposal existed."
    } catch {
        $statusCode = $null
        try {
            $statusCode = $_.Exception.Response.StatusCode.value__
        } catch {
        }
        $detail = $_.ErrorDetails.Message
        if ($statusCode -ne 409) {
            $checks.send_guard.status = "failed"
            $checks.send_guard.details = @{
                statusCode = $statusCode
                detail = $detail
            }
            throw "Send guard did not return expected 409."
        }
        $checks.send_guard.status = "success"
        $checks.send_guard.details = @{
            statusCode = $statusCode
            detail = $detail
        }
    }

    $patchedSummary = "Smoke test manual summary for final proposal."
    $patchedMargin = 4321.0
    $patchPayload = @{
        summary = $patchedSummary
        margin = $patchedMargin
    } | ConvertTo-Json
    $patchedDetail = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/proposal-draft" -Method Patch -ContentType "application/json" -Body $patchPayload -TimeoutSec 15
    if ($patchedDetail.proposalDraft.summary -ne $patchedSummary) {
        throw "Proposal draft summary patch was not applied."
    }
    $checks.draft_patch.status = "success"
    $checks.draft_patch.details = @{
        summary = $patchedDetail.proposalDraft.summary
        margin = $patchedDetail.proposalDraft.margin
    }

    $finalDetail = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/final-proposal" -Method Post -TimeoutSec 20
    if ($null -eq $finalDetail.finalProposal) {
        throw "Final proposal payload is missing."
    }
    if ($finalDetail.finalProposal.summary -ne $patchedSummary) {
        throw "Final proposal did not carry patched draft summary."
    }
    $checks.final_proposal.status = "success"
    $checks.final_proposal.details = @{
        id = $finalDetail.finalProposal.id
        summary = $finalDetail.finalProposal.summary
        status = $finalDetail.finalProposal.status
    }

    $sentDetail = Invoke-RestMethod -Uri "$casesUrl/$duplicateCaseId/send" -Method Post -TimeoutSec 15
    if ($sentDetail.status -ne "sent") {
        throw "Case was not marked as sent."
    }
    $checks.send_after_final.status = "success"
    $checks.send_after_final.details = @{
        status = $sentDetail.status
        finalProposalStatus = $sentDetail.finalProposal.status
    }

    & python $cleanupScript --project-id $duplicateCaseId --allow-prefix prj_
    if ($LASTEXITCODE -ne 0) {
        throw "Cleanup helper failed with exit code $LASTEXITCODE."
    }
    $checks.cleanup.status = "success"
    $checks.cleanup.details = @{
        deletedProjectId = $duplicateCaseId
    }

    Write-SmokeStatus -Status "success" -Message "Draft patch / send guard smoke workflow passed." -Checks $checks
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
