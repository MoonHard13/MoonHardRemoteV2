param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^\d+\.\d+\.\d+$")]
    [string]$Version
)

$ErrorActionPreference = "Stop"

# Backwards-compatible wrapper.
# The canonical update package builder now always includes and validates
# the required SQL resources.
& (Join-Path $PSScriptRoot "build_client_update_package.ps1") -Version $Version

if ($LASTEXITCODE -ne 0) {
    throw "Client update package build failed."
}
