param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+$")]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$AppName = "MoonHardRemoteClient"
$ClientConfigPath = Join-Path $ProjectRoot "client\app\config.py"
$ClientDistDir = Join-Path $ProjectRoot "dist\$AppName"
$ReleaseRoot = Join-Path $ProjectRoot "release_packages\client-v$Version"
$PackageZip = Join-Path $ReleaseRoot "moonhard-client-$Version.zip"
$PackageShaFile = Join-Path $ReleaseRoot "moonhard-client-$Version.sha256.txt"

if (-not (Test-Path $ClientConfigPath)) {
    throw "Missing client config file: $ClientConfigPath"
}

$ClientConfigContent = Get-Content $ClientConfigPath -Raw
if ($ClientConfigContent -notmatch "self\.app_version\s*=\s*`"$Version`"") {
    throw "client/app/config.py does not contain app_version $Version."
}

Write-Host "Building resource-aware MoonHard client..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "build_client_exe.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Client build failed."
}

$BuiltExe = Join-Path $ClientDistDir "$AppName.exe"
$SqlResourceDir = Join-Path $ClientDistDir "_internal\app\sql"
if (-not (Test-Path $BuiltExe)) {
    throw "Missing client EXE: $BuiltExe"
}
if (-not (Test-Path $SqlResourceDir)) {
    throw "Missing packaged SQL resources: $SqlResourceDir"
}

New-Item -ItemType Directory -Force $ReleaseRoot | Out-Null
if (Test-Path $PackageZip) {
    Remove-Item $PackageZip -Force
}

Push-Location $ClientDistDir

try {
    tar.exe -a -c -f $PackageZip *

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create client update ZIP."
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $PackageZip)) {
    throw "Package ZIP was not created: $PackageZip"
}

$PackageContents = tar.exe -tf $PackageZip

if (-not ($PackageContents -match "_internal/base_library.zip")) {
    throw "Package validation failed: _internal/base_library.zip is missing."
}

if (-not ($PackageContents -match "MoonHardRemoteClient.exe")) {
    throw "Package validation failed: MoonHardRemoteClient.exe is missing."
}

$Sha256 = (Get-FileHash -Algorithm SHA256 $PackageZip).Hash.ToUpperInvariant()
Set-Content -Path $PackageShaFile -Value $Sha256 -Encoding ASCII

Write-Host "Update package created successfully." -ForegroundColor Green
Write-Host "Package: $PackageZip" -ForegroundColor Green
Write-Host "SHA256:  $Sha256" -ForegroundColor Green
Write-Host "Release tag: client-v$Version" -ForegroundColor Cyan
