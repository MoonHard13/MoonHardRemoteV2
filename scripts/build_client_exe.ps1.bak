$ErrorActionPreference = "Stop"

# Πηγαίνει στο root του project
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Building MoonHardRemoteClient.exe..." -ForegroundColor Cyan

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name MoonHardRemoteClient `
  --console `
  --paths .\client `
  --add-data ".\client\app\sql;app\sql" `
  .\client\app\main.py

if ($LASTEXITCODE -ne 0) { throw "Αποτυχία build του Client." }

Write-Host "Build completed." -ForegroundColor Green
Write-Host "Output: dist\MoonHardRemoteClient\MoonHardRemoteClient.exe" -ForegroundColor Green
