param(
    [Parameter(Mandatory)][string]$Version
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
if ($Version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw 'Use a plain release version without paths.' }
Push-Location $projectRoot
try {
    & (Join-Path $PSScriptRoot 'build.ps1')
    & (Join-Path $PSScriptRoot 'package.ps1')
    & (Join-Path $PSScriptRoot 'export-source.ps1') -Version $Version
    $python = Join-Path $projectRoot '.work/vendor/python-embed/python.exe'
    & $python -B (Join-Path $PSScriptRoot 'verify-release.py') --version $Version
    if ($LASTEXITCODE) { throw 'Release verification failed; do not upload the assets.' }
} finally { Pop-Location }
