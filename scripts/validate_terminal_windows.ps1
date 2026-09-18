$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Ελέγχει το πραγματικό CMD/PowerShell και το πραγματικό Tk widget πριν το build.
python -m unittest discover -s tests -p "test_terminal_sessions.py" -v
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία ελέγχων μόνιμων συνεδριών." }
python -m unittest discover -s tests -p "test_terminal_ui.py" -v
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία ελέγχων GUI." }

& "$PSScriptRoot\build_dashboard_exe.ps1"
& "$PSScriptRoot\build_client_exe.ps1"

# Δοκιμάζει τα EXE από καθαρό directory χωρίς source code και χωρίς σύνδεση σε remote Client.
$SmokeFolder = Join-Path ([System.IO.Path]::GetTempPath()) ("MoonHardTerminalSmoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $SmokeFolder | Out-Null
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteDashboard.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteTerminal.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteClient") $SmokeFolder -Recurse
$ReportPath = Join-Path $SmokeFolder "terminal-smoke-result.json"
$Process = Start-Process -FilePath (Join-Path $SmokeFolder "MoonHardRemoteDashboard.exe") `
    -ArgumentList @("--terminal-self-test", ('"' + $ReportPath + '"')) `
    -WorkingDirectory $SmokeFolder -PassThru
if (-not $Process.WaitForExit(60000)) {
    Stop-Process -Id $Process.Id -Force
    throw "Έληξε η αναμονή ελέγχου EXE."
}
if ($Process.ExitCode -ne 0) { throw "Αποτυχία ελέγχου EXE. Αναφορά: $ReportPath" }
$Report = Get-Content $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.success) { throw "Η αναφορά EXE δεν επιβεβαιώνει επιτυχή έλεγχο." }

$ClientReportPath = Join-Path $SmokeFolder "client-terminal-smoke-result.json"
$ClientProcess = Start-Process -FilePath (Join-Path $SmokeFolder "MoonHardRemoteClient\MoonHardRemoteClient.exe") `
    -ArgumentList @("--terminal-self-test", ('"' + $ClientReportPath + '"')) `
    -WorkingDirectory $SmokeFolder -PassThru
if (-not $ClientProcess.WaitForExit(60000)) {
    Stop-Process -Id $ClientProcess.Id -Force
    throw "Έληξε η αναμονή ελέγχου Client EXE."
}
if ($ClientProcess.ExitCode -ne 0) { throw "Αποτυχία ελέγχου Client EXE. Αναφορά: $ClientReportPath" }
$ClientReport = Get-Content $ClientReportPath -Raw | ConvertFrom-Json
if (-not $ClientReport.success) { throw "Αποτυχία ελέγχου των συσκευασμένων native shells." }

Push-Location $SmokeFolder
try {
    & .\MoonHardRemoteTerminal.exe --help
    if ($LASTEXITCODE -ne 0) { throw "Αποτυχία Terminal CLI EXE." }
} finally {
    Pop-Location
}
Write-Host "Επιτυχής έλεγχος EXE. Αναφορά: $ReportPath" -ForegroundColor Green
