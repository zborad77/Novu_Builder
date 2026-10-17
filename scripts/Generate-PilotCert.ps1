#Requires -Version 5.1
# Generate a self-signed TLS certificate for local pilot deployment (Windows).
#
# Usage:
#   .\scripts\Generate-PilotCert.ps1                 # localhost + 127.0.0.1 only
#   .\scripts\Generate-PilotCert.ps1 -ExtraIP 192.168.1.50
#
# Output: nginx\certs\cert.pem  nginx\certs\key.pem
# Requires openssl.exe (Qt Tools or Git for Windows ship it).

param(
    [string]$ExtraIP = ""
)

$ErrorActionPreference = "Stop"
$rootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$certDir = Join-Path $rootDir "nginx\certs"

function Find-OpenSSL {
    $candidates = @(
        "C:\Qt\Tools\OpenSSLv3\Win_x64\bin\openssl.exe",
        "C:\Program Files\Git\usr\bin\openssl.exe",
        "C:\Program Files\OpenSSL-Win64\bin\openssl.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $inPath = Get-Command openssl.exe -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }
    return $null
}

$openssl = Find-OpenSSL
if (-not $openssl) {
    Write-Error @"
openssl.exe not found. Install one of:
  - Qt Tools OpenSSL:   C:\Qt\Tools\OpenSSLv3\Win_x64\bin\openssl.exe
  - Git for Windows:    C:\Program Files\Git\usr\bin\openssl.exe
  - OpenSSL for Win64:  https://slproweb.com/products/Win32OpenSSL.html
"@
    exit 1
}

New-Item -ItemType Directory -Force -Path $certDir | Out-Null

$days = 825
$san  = "IP:127.0.0.1,DNS:localhost"
if ($ExtraIP -ne "") {
    $san += ",IP:$ExtraIP"
    Write-Host "-> Including extra IP in SAN: $ExtraIP"
}

Write-Host "-> openssl: $openssl"
Write-Host "-> Generating self-signed cert ($days days, SAN: $san)"

$certPath = Join-Path $certDir "cert.pem"
$keyPath  = Join-Path $certDir "key.pem"

$tmpConf = [System.IO.Path]::GetTempFileName()
try {
    @"
[req]
distinguished_name = dn
x509_extensions    = v3_req
prompt             = no

[dn]
O  = NOVU Builder Internal
CN = novu-pilot

[v3_req]
subjectAltName   = $san
basicConstraints = CA:FALSE
keyUsage         = digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
"@ | Set-Content -Path $tmpConf -Encoding UTF8

    & $openssl req -x509 `
        -nodes `
        -days $days `
        -newkey rsa:2048 `
        -keyout $keyPath `
        -out    $certPath `
        -config $tmpConf
    if ($LASTEXITCODE -ne 0) {
        throw "openssl exited with code $LASTEXITCODE"
    }
} finally {
    Remove-Item $tmpConf -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Cert generated:"
Write-Host "  $certPath"
Write-Host "  $keyPath"
Write-Host ""

$validity = & $openssl x509 -noout -enddate -in $certPath
Write-Host "  Validity : $validity"

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. .\scripts\Trust-PilotCert.ps1"
Write-Host "  2. .\scripts\Build-ComposeEnv.ps1 -Write  <- merge env files -> root .env.production"
Write-Host "  3. docker compose --env-file .env.production up -d"
Write-Host "  4. .\desktop-qt\scripts\smoke-check.ps1"
Write-Host "  5. Open NovuBuilder.exe -> server URL: https://localhost"
