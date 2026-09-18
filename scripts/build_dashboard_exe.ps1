$ErrorActionPreference = "Stop"

# Εντοπίζει απόλυτα τον φάκελο του project χωρίς εξάρτηση από το τρέχον directory.
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Συμπεριλαμβάνει widgets, assets και όλα τα CLI modules χωρίς να ενσωματώνει μυστικά .env.
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name MoonHardRemoteDashboard --paths .\dashboard --collect-all customtkinter `
    --hidden-import app.terminal_cli --hidden-import app.terminal_smoke `
    --hidden-import app.backup_cli --hidden-import app.database_cli `
    --hidden-import app.provider_transmitted_cli `
    --icon .\dashboard\assets\MoonHardRemoteDashboard.ico `
    --add-data ".\dashboard\assets;assets" .\dashboard\app\main.py
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία build του Dashboard." }

# Παρέχει χωριστό console EXE για CLI, ανακατευθύνσεις και αυτοματισμούς από CMD.
python -m PyInstaller --noconfirm --clean --onefile --console `
    --name MoonHardRemoteTerminal --paths .\dashboard .\dashboard\app\terminal_cli.py
if ($LASTEXITCODE -ne 0) { throw "Αποτυχία build του Terminal CLI." }
