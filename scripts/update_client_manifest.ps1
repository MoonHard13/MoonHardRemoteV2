param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+$")]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$Sha256,

    [Parameter(Mandatory = $false)]
    [string]$ReleaseNotes = "Security update and client stability improvements.",

    [Parameter(Mandatory = $false)]
    [switch]$Mandatory
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ManifestPath = Join-Path $ProjectRoot "server\app\update_manifest.json"
$DownloadUrl = "https://github.com/MoonHard13/MoonHardRemoteV2/releases/download/client-v$Version/moonhard-client-$Version.zip"

if (-not (Test-Path $ManifestPath)) {
    throw "Manifest file was not found: $ManifestPath"
}

$Manifest = [ordered]@{
    product = "moonhard-remote-client"
    latest_version = $Version
    download_url = $DownloadUrl
    sha256 = $Sha256.ToUpperInvariant()
    mandatory = [bool]$Mandatory
    release_notes = $ReleaseNotes
}

$Json = $Manifest | ConvertTo-Json -Depth 5

Set-Content `
    -Path $ManifestPath `
    -Value $Json `
    -Encoding UTF8

Write-Host "Manifest updated successfully." -ForegroundColor Green
Write-Host "Path: $ManifestPath" -ForegroundColor Gray
Write-Host "Version: $Version" -ForegroundColor Gray
Write-Host "Download URL: $DownloadUrl" -ForegroundColor Gray
Write-Host "SHA256: $($Sha256.ToUpperInvariant())" -ForegroundColor Gray
Write-Host "Mandatory: $([bool]$Mandatory)" -ForegroundColor Gray