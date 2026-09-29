$ErrorActionPreference = "Stop"

# Find project root and switch to it.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Building MoonHard Remote Dashboard..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name MoonHardRemoteDashboard `
    --paths .\dashboard `
    --collect-all customtkinter `
    --hidden-import app.terminal_cli `
    --hidden-import app.terminal_smoke `
    --hidden-import app.backup_cli `
    --hidden-import app.database_cli `
    --hidden-import app.provider_transmitted_cli `
    --hidden-import app.appsettings_cli `
    --hidden-import app.appsettings_smoke `
    --hidden-import app.sql_cli `
    --hidden-import app.sql_smoke `
    --hidden-import app.overview_cli `
    --hidden-import app.overview_smoke `
    --icon .\dashboard\assets\MoonHardRemoteDashboard.ico `
    --add-data ".\dashboard\assets;assets" `
    .\dashboard\app\main.py

if ($LASTEXITCODE -ne 0) {
    throw "Dashboard build failed."
}

Write-Host "Dashboard build completed." -ForegroundColor Green
Write-Host "Output: dist\MoonHardRemoteDashboard.exe" -ForegroundColor Green


Write-Host ""
Write-Host "Building Terminal CLI..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MoonHardRemoteTerminal `
    --paths .\dashboard `
    .\dashboard\app\terminal_cli.py

if ($LASTEXITCODE -ne 0) {
    throw "Terminal build failed."
}


Write-Host ""
Write-Host "Building AppSettings CLI..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MoonHardRemoteAppSettings `
    --paths .\dashboard `
    .\dashboard\app\appsettings_cli.py

if ($LASTEXITCODE -ne 0) {
    throw "AppSettings build failed."
}


Write-Host ""
Write-Host "Building SSMS CLI..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MoonHardRemoteSSMS `
    --paths .\dashboard `
    .\dashboard\app\sql_cli.py

if ($LASTEXITCODE -ne 0) {
    throw "SSMS build failed."
}


Write-Host ""
Write-Host "Building Overview CLI..." -ForegroundColor Cyan

python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MoonHardRemoteOverview `
    --paths .\dashboard `
    .\dashboard\app\overview_cli.py

if ($LASTEXITCODE -ne 0) {
    throw "Overview build failed."
}

Write-Host ""
Write-Host "All Dashboard executables built successfully." -ForegroundColor Green