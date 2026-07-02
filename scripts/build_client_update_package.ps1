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
$ValidationDir = Join-Path $ProjectRoot "release_packages\_validate_client_v$Version"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MoonHard Remote Client Update Package" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Version: $Version" -ForegroundColor Gray
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray

if (-not (Test-Path $ClientConfigPath)) {
    throw "Missing client config file: $ClientConfigPath"
}

$ClientConfigContent = Get-Content $ClientConfigPath -Raw

if ($ClientConfigContent -notmatch "self\.app_version\s*=\s*`"$Version`"") {
    throw "client/app/config.py does not contain app_version $Version. Update ClientConfig.app_version first."
}

Write-Host ""
Write-Host "Step 1/6 - Installing pinned requirements..." -ForegroundColor Cyan

python -m pip install --upgrade pip
python -m pip install -r .\client\requirements.txt
python -m pip install -r .\updater\requirements.txt

Write-Host "Pinned requirements installed." -ForegroundColor Green

Write-Host ""
Write-Host "Step 2/6 - Cleaning build output..." -ForegroundColor Cyan

Remove-Item (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ProjectRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ProjectRoot "$AppName.spec") -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Step 3/6 - Building client EXE with PyInstaller..." -ForegroundColor Cyan

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name $AppName `
  --console `
  --paths .\client `
  --collect-data certifi `
  .\client\app\main.py

$BuiltExe = Join-Path $ClientDistDir "$AppName.exe"
$BuiltInternalDir = Join-Path $ClientDistDir "_internal"

if (-not (Test-Path $BuiltExe)) {
    throw "PyInstaller build failed. Missing EXE: $BuiltExe"
}

if (-not (Test-Path $BuiltInternalDir)) {
    throw "PyInstaller build failed. Missing _internal folder: $BuiltInternalDir"
}

Write-Host "Client EXE built: $BuiltExe" -ForegroundColor Green

Write-Host ""
Write-Host "Step 4/6 - Creating release package folder..." -ForegroundColor Cyan

Remove-Item $ReleaseRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $ReleaseRoot | Out-Null

Write-Host ""
Write-Host "Step 5/6 - Creating update ZIP..." -ForegroundColor Cyan

Compress-Archive `
    -Path (Join-Path $ClientDistDir "*") `
    -DestinationPath $PackageZip `
    -Force

if (-not (Test-Path $PackageZip)) {
    throw "Package ZIP was not created: $PackageZip"
}

Remove-Item $ValidationDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $ValidationDir | Out-Null

Expand-Archive `
    -Path $PackageZip `
    -DestinationPath $ValidationDir `
    -Force

if (-not (Test-Path (Join-Path $ValidationDir "MoonHardRemoteClient.exe"))) {
    throw "ZIP validation failed. Missing MoonHardRemoteClient.exe in ZIP root."
}

if (-not (Test-Path (Join-Path $ValidationDir "_internal"))) {
    throw "ZIP validation failed. Missing _internal folder in ZIP root."
}

Remove-Item $ValidationDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "ZIP package created and validated: $PackageZip" -ForegroundColor Green

Write-Host ""
Write-Host "Step 6/6 - Calculating SHA256..." -ForegroundColor Cyan

$Sha256 = (Get-FileHash -Algorithm SHA256 $PackageZip).Hash.ToUpperInvariant()

Set-Content `
    -Path $PackageShaFile `
    -Value $Sha256 `
    -Encoding ASCII

Write-Host ""
Write-Host "Build completed successfully." -ForegroundColor Green
Write-Host "Package: $PackageZip" -ForegroundColor Green
Write-Host "SHA256:  $Sha256" -ForegroundColor Green
Write-Host ""
Write-Host "GitHub release tag:" -ForegroundColor Cyan
Write-Host "client-v$Version"
Write-Host ""
Write-Host "Expected download URL:" -ForegroundColor Cyan
Write-Host "https://github.com/MoonHard13/MoonHardRemoteV2/releases/download/client-v$Version/moonhard-client-$Version.zip"
Write-Host ""