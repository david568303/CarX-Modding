param([switch]$DebugNative)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Path (Join-Path $projectRoot '.work/build') -Force | Out-Null
& (Join-Path $PSScriptRoot 'prepare-python.ps1')
& (Join-Path $PSScriptRoot 'prepare-bepinex.ps1')
& (Join-Path $PSScriptRoot 'build-doorstop.ps1') -Release:(-not $DebugNative)
& dotnet build (Join-Path $projectRoot 'src/MetadataBootstrap/MetadataBootstrap.csproj') -c Release --nologo
if ($LASTEXITCODE -ne 0) { throw 'Metadata bootstrap build failed.' }
