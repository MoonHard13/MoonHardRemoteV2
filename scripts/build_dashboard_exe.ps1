param([switch]$CLI)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $projectRoot "dashboard")
try {
    # Διατηρούμε ξεχωριστό console build για πραγματική έξοδο CLI/CMD.
    $appName = if ($CLI) { "MoonHardDashboardCLI" } else { "MoonHardRemoteDashboard" }
    $mode = if ($CLI) { "--console" } else { "--windowed" }
    $arguments = @(
        "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", $mode,
        "--name", $appName, "--paths", ".",
        "--collect-all", "customtkinter",
        "--hidden-import", "app.backup_cli",
        "--hidden-import", "app.database_cli",
        "--hidden-import", "app.provider_transmitted_cli",
        "--hidden-import", "app.provider_diagnostic.cli",
        "--add-data", "assets;assets",
        "--icon", "assets/MoonHardRemoteDashboard.ico", "app/main.py"
    )
    # Δεν ενσωματώνουμε .env ή πραγματικά credentials στο εκτελέσιμο.
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Dashboard PyInstaller build failed." }
} finally {
    Pop-Location
}
