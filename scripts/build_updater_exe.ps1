$ErrorActionPreference = "Stop"

# Πηγαίνει στο root του project
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$AppName = "MoonHardUpdater"

Write-Host "Building MoonHardUpdater.exe..." -ForegroundColor Cyan

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name $AppName `
  --console `
  --paths .\updater `
  .\updater\app\update_runner.py

$UpdaterExe = Join-Path $ProjectRoot "dist\$AppName.exe"

if (-not (Test-Path $UpdaterExe)) {
    throw "Updater build failed. Missing EXE: $UpdaterExe"
}

Write-Host "Build completed." -ForegroundColor Green
Write-Host "Output: $UpdaterExe" -ForegroundColor Green