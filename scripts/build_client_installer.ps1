$ErrorActionPreference = "Stop"

# Πηγαίνει στο root του project
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$AppName = "MoonHardRemoteClient"
$InstallerScript = Join-Path $ProjectRoot "installer\MoonHardRemoteClientSetup.iss"
$InstallerClientFilesDir = Join-Path $ProjectRoot "installer\client_files"
$InstallerOutputDir = Join-Path $ProjectRoot "installer\output"
$ClientDistDir = Join-Path $ProjectRoot "dist\$AppName"
$WinSWSource = Join-Path $ProjectRoot "tools\winsw\MoonHardRemoteClientService.exe"
$WinSWDestination = Join-Path $InstallerClientFilesDir "MoonHardRemoteClientService.exe"
$ServiceXml = Join-Path $InstallerClientFilesDir "MoonHardRemoteClientService.xml"
$SecretFile = Join-Path $ProjectRoot "installer\secrets\client_token.iss"
$UpdaterAppName = "MoonHardUpdater"
$UpdaterDistDir = Join-Path $ProjectRoot "dist\$UpdaterAppName"
$UpdaterBuiltExe = Join-Path $UpdaterDistDir "$UpdaterAppName.exe"
$UpdaterDestination = Join-Path $InstallerClientFilesDir "$UpdaterAppName.exe"

$InnoCompilerCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$InnoCompiler = $null

foreach ($Candidate in $InnoCompilerCandidates) {
    if (Test-Path $Candidate) {
        $InnoCompiler = $Candidate
        break
    }
}

if (-not $InnoCompiler) {
    throw "Inno Setup compiler was not found. Expected ISCC.exe in Program Files or Program Files (x86)."
}

if (-not (Test-Path $SecretFile)) {
    throw "Missing installer secret file: $SecretFile"
}

if (-not (Test-Path $WinSWSource)) {
    throw "Missing WinSW service wrapper: $WinSWSource"
}

if (-not (Test-Path $ServiceXml)) {
    throw "Missing WinSW XML file: $ServiceXml"
}

if (-not (Test-Path $InstallerScript)) {
    throw "Missing Inno Setup script: $InstallerScript"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MoonHard Remote Client Installer Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray
Write-Host "Inno compiler: $InnoCompiler" -ForegroundColor Gray

Write-Host ""
Write-Host "Step 1/6 - Cleaning PyInstaller output..." -ForegroundColor Cyan

Remove-Item (Join-Path $ProjectRoot "build") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ProjectRoot "dist") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $ProjectRoot "$AppName.spec") -Force -ErrorAction SilentlyContinue

Write-Host "Step 2/6 - Building client EXE with PyInstaller..." -ForegroundColor Cyan

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name $AppName `
  --console `
  --paths .\client `
  .\client\app\main.py

$BuiltExe = Join-Path $ClientDistDir "$AppName.exe"

if (-not (Test-Path $BuiltExe)) {
    throw "PyInstaller build failed. Missing EXE: $BuiltExe"
}

Write-Host ""
Write-Host "Step 2B - Building updater EXE with PyInstaller..." -ForegroundColor Cyan

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name $UpdaterAppName `
  --console `
  --paths .\updater `
  .\updater\app\update_runner.py

if (-not (Test-Path $UpdaterBuiltExe)) {
    throw "Updater PyInstaller build failed. Missing EXE: $UpdaterBuiltExe"
}

Write-Host "Updater EXE built: $UpdaterBuiltExe" -ForegroundColor Green

Write-Host "Client EXE built: $BuiltExe" -ForegroundColor Green

Write-Host ""
Write-Host "Step 3/6 - Preparing installer client_files folder..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force $InstallerClientFilesDir | Out-Null
Remove-Item (Join-Path $InstallerClientFilesDir "_internal") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $InstallerClientFilesDir "$AppName.exe") -Force -ErrorAction SilentlyContinue
Remove-Item $UpdaterDestination -Force -ErrorAction SilentlyContinue
Remove-Item $WinSWDestination -Force -ErrorAction SilentlyContinue

Copy-Item (Join-Path $ClientDistDir "*") $InstallerClientFilesDir -Recurse -Force
Copy-Item $UpdaterBuiltExe $UpdaterDestination -Force
Copy-Item $WinSWSource $WinSWDestination -Force

if (-not (Test-Path (Join-Path $InstallerClientFilesDir "$AppName.exe"))) {
    throw "Installer payload missing client EXE."
}

if (-not (Test-Path $UpdaterDestination)) {
    throw "Installer payload missing updater EXE."
}

if (-not (Test-Path $WinSWDestination)) {
    throw "Installer payload missing WinSW wrapper."
}

if (-not (Test-Path $ServiceXml)) {
    throw "Installer payload missing service XML."
}

Write-Host "Installer payload prepared." -ForegroundColor Green

Write-Host ""
Write-Host "Step 4/6 - Cleaning installer output..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force $InstallerOutputDir | Out-Null
Remove-Item (Join-Path $InstallerOutputDir "*") -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Step 5/6 - Compiling Inno Setup installer..." -ForegroundColor Cyan

& $InnoCompiler $InstallerScript

$SetupExe = Join-Path $InstallerOutputDir "MoonHardRemoteClientSetup.exe"

if (-not (Test-Path $SetupExe)) {
    throw "Installer compile failed. Missing setup EXE: $SetupExe"
}

Write-Host ""
Write-Host "Step 6/6 - Build completed successfully." -ForegroundColor Green
Write-Host "Output: $SetupExe" -ForegroundColor Green
Write-Host ""