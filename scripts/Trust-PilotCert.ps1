#Requires -Version 5.1
# Add the pilot self-signed cert to the current user's Trusted Root CA store.
# No admin rights required — this is a user-level store (certutil -user flag).
#
# Usage:
#   .\scripts\Trust-PilotCert.ps1
#
# To undo:
#   certutil -delstore -user Root novu-pilot

$ErrorActionPreference = "Stop"
$rootDir  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$certPath = Join-Path $rootDir "nginx\certs\cert.pem"

if (-not (Test-Path $certPath)) {
    Write-Error "cert.pem not found at: $certPath`nRun .\scripts\Generate-PilotCert.ps1 first."
    exit 1
}

Write-Host "Adding $certPath to user Trusted Root CA store..."
certutil -addstore -user Root $certPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "certutil failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Qt client and PowerShell will now trust https://localhost."
Write-Host "To remove later: certutil -delstore -user Root novu-pilot"
