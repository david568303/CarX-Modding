param(
    [Parameter(Mandatory)][string]$CapstoneIncludeDir,
    [switch]$Release
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$sourceRoot = Join-Path $projectRoot 'src/Doorstop'
$builder = Join-Path $sourceRoot 'build-msvc.ps1'
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
    throw 'Initialize the pinned Doorstop submodule before building.'
}
& $builder -Release:$Release -CapstoneIncludeDir $CapstoneIncludeDir -BuildRoot (Join-Path $projectRoot '.work/build/doorstop-x64')
