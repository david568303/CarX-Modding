param(
    [Parameter(Mandatory)][string]$CapstoneIncludeDir,
    [switch]$DebugNative
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
New-Item -ItemType Directory -Path (Join-Path $projectRoot '.work/build') -Force | Out-Null
$officialRuntime = & (Join-Path $PSScriptRoot 'prepare-bepinex.ps1')
$bepInExCore = Join-Path $officialRuntime 'BepInEx/core'
& (Join-Path $PSScriptRoot 'build-doorstop.ps1') -CapstoneIncludeDir $CapstoneIncludeDir -Release:(-not $DebugNative)
& dotnet build (Join-Path $projectRoot 'src/MetadataBootstrap/MetadataBootstrap.csproj') -c Release --nologo "-p:BepInExCoreDirectory=$bepInExCore"
if ($LASTEXITCODE -ne 0) { throw 'Metadata bootstrap build failed.' }
