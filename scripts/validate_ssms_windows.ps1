$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Ελέγχει το SSMS και τις δύο προηγούμενες αλλαγές του Manage window.
foreach ($Pattern in @("test_sql_execution.py", "test_ssms.py", "test_appsettings.py", "test_terminal_ui.py")) {
    python -m unittest discover -s tests -p $Pattern -v
    if ($LASTEXITCODE -ne 0) { throw "Αποτυχία δοκιμών $Pattern." }
}
& "$PSScriptRoot\build_dashboard_exe.ps1"
& "$PSScriptRoot\build_client_exe.ps1"

# Απομονώνει τα πραγματικά EXE σε καθαρό φάκελο χωρίς source και χωρίς παραγωγικό server.
$SmokeFolder = Join-Path ([System.IO.Path]::GetTempPath()) ("MoonHardSSMS-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $SmokeFolder | Out-Null
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteDashboard.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteSSMS.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteClient") $SmokeFolder -Recurse
$ClientReport = Join-Path $SmokeFolder "sql-client-smoke.json"
& (Join-Path $SmokeFolder "MoonHardRemoteClient\MoonHardRemoteClient.exe") --sql-self-test $ClientReport
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία SQL Client EXE." }
$ClientChecks = Get-Content $ClientReport -Raw | ConvertFrom-Json
if (-not $ClientChecks.success) { throw "Αποτυχία αποτελεσμάτων/timeout Client EXE." }
Copy-Item $ClientReport (Join-Path $ProjectRoot "dist\sql-client-smoke.json")
$ReportPath = Join-Path $SmokeFolder "ssms-smoke.json"
$Process = Start-Process -FilePath (Join-Path $SmokeFolder "MoonHardRemoteDashboard.exe") `
    -ArgumentList @("--ssms-self-test", ('"' + $ReportPath + '"')) `
    -WorkingDirectory $SmokeFolder -PassThru
if (-not $Process.WaitForExit(60000)) {
    Stop-Process -Id $Process.Id -Force
    throw "Έληξε η αναμονή Dashboard EXE."
}
if ($Process.ExitCode -ne 0) { throw "Αποτυχία Dashboard EXE. Αναφορά: $ReportPath" }
$Report = Get-Content $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.success) { throw "Αποτυχία ελέγχου SSMS μέσα στο Dashboard EXE." }
python "$PSScriptRoot\smoke_ssms_cli.py" (Join-Path $SmokeFolder "MoonHardRemoteSSMS.exe") $SmokeFolder
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία SSMS CLI EXE." }
Copy-Item $ReportPath (Join-Path $ProjectRoot "dist\ssms-smoke.json")
$PreviewPath = [System.IO.Path]::ChangeExtension($ReportPath, ".png")
if (Test-Path $PreviewPath) { Copy-Item $PreviewPath (Join-Path $ProjectRoot "dist\ssms-preview.png") }
Write-Host "Επιτυχής έλεγχος SSMS EXE." -ForegroundColor Green
