$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Ελέγχει τη νέα προβολή και την προηγούμενη λειτουργικότητα του Terminal.
python -m unittest discover -s tests -p "test_appsettings.py" -v
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία ελέγχων AppSettings." }
python -m unittest discover -s tests -p "test_terminal_ui.py" -v
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία ελέγχων Terminal." }
& "$PSScriptRoot\build_dashboard_exe.ps1"

# Αντιγράφει τα EXE σε καθαρό φάκελο χωρίς source code ή στοιχεία πελατών.
$SmokeFolder = Join-Path ([System.IO.Path]::GetTempPath()) ("MoonHardAppSettings-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $SmokeFolder | Out-Null
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteDashboard.exe") $SmokeFolder
Copy-Item (Join-Path $ProjectRoot "dist\MoonHardRemoteAppSettings.exe") $SmokeFolder
$ReportPath = Join-Path $SmokeFolder "appsettings-smoke.json"
$Process = Start-Process -FilePath (Join-Path $SmokeFolder "MoonHardRemoteDashboard.exe") `
    -ArgumentList @("--appsettings-self-test", ('"' + $ReportPath + '"')) `
    -WorkingDirectory $SmokeFolder -PassThru
if (-not $Process.WaitForExit(60000)) {
    Stop-Process -Id $Process.Id -Force
    throw "Έληξε η αναμονή ελέγχου Dashboard EXE."
}
if ($Process.ExitCode -ne 0) { throw "Αποτυχία Dashboard EXE. Αναφορά: $ReportPath" }
$Report = Get-Content $ReportPath -Raw | ConvertFrom-Json
if (-not $Report.success) { throw "Αποτυχία πραγματικού AppSettings UI μέσα στο EXE." }

# Δοκιμάζει αυθεντικοποίηση και ανάκτηση JSON του console EXE σε τοπικό προσωρινό server.
python "$PSScriptRoot\smoke_appsettings_cli.py" (Join-Path $SmokeFolder "MoonHardRemoteAppSettings.exe") $SmokeFolder
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία AppSettings CLI EXE." }
Copy-Item $ReportPath (Join-Path $ProjectRoot "dist\appsettings-smoke.json")
Write-Host "Επιτυχής έλεγχος AppSettings EXE." -ForegroundColor Green
