$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Η αλλαγή Manage επηρεάζει τον χώρο εργασίας κάθε καρτέλας.
foreach ($Pattern in @("test_overview.py", "test_sql_execution.py", "test_ssms.py", "test_appsettings.py", "test_terminal_ui.py")) {
    python -m unittest discover -s tests -p $Pattern -v
    if ($LASTEXITCODE -ne 0) { throw "Αποτυχία δοκιμών $Pattern." }
}
& "$PSScriptRoot\build_dashboard_exe.ps1"
$SmokeFolder = Join-Path ([System.IO.Path]::GetTempPath()) ("MoonHardOverview-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $SmokeFolder | Out-Null
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteDashboard.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteOverview.exe") $SmokeFolder
$ReportPath = Join-Path $SmokeFolder "overview-smoke.json"
$Process = Start-Process -FilePath (Join-Path $SmokeFolder "MoonHardRemoteDashboard.exe") `
    -ArgumentList @("--overview-self-test", ('"' + $ReportPath + '"')) `
    -WorkingDirectory $SmokeFolder -PassThru
if (-not $Process.WaitForExit(60000)) {
    Stop-Process -Id $Process.Id -Force
    throw "Έληξε η αναμονή Dashboard EXE."
}
if ($Process.ExitCode -ne 0) { throw "Αποτυχία Overview Dashboard EXE." }
$Report = Get-Content $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.success) { throw "Αποτυχία ελέγχου Overview." }
python "$PSScriptRoot\smoke_overview_cli.py" (Join-Path $SmokeFolder "MoonHardRemoteOverview.exe") $SmokeFolder
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία Overview CLI EXE." }
Copy-Item $ReportPath (Join-Path $ProjectRoot "dist\overview-smoke.json")
$Preview = [System.IO.Path]::ChangeExtension($ReportPath, ".png")
if (Test-Path $Preview) { Copy-Item $Preview (Join-Path $ProjectRoot "dist\overview-preview.png") }
Write-Host "Επιτυχής έλεγχος Overview EXE." -ForegroundColor Green
