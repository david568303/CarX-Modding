param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9]+(\.[0-9]+){2,3}$')][string]$Version,
    [string]$Destination,
    [string]$ReviewedRuntimeZip,
    [string]$CapstoneIncludeDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent

if ([bool]$ReviewedRuntimeZip -ne [bool]$CapstoneIncludeDir) {
    throw 'Pass both the reviewed runtime ZIP and its matching Capstone 5.0.9 headers, or neither to build dependencies from source.'
}
$scratch = Join-Path ([IO.Path]::GetTempPath()) ('carx-' + [Guid]::NewGuid().ToString('N').Substring(0,12))
New-Item -ItemType Directory -Path $scratch | Out-Null

if ($ReviewedRuntimeZip) {
    $runtime = (Resolve-Path -LiteralPath $ReviewedRuntimeZip).Path
    $expected = '6a308327941689f6899a73dc2592ffa8738298582e0a4ea445a723f9c671da59'
    if ((Get-FileHash -LiteralPath $runtime).Hash -ine $expected) {
        throw 'ReviewedRuntimeZip is not the immutable 2026.11.07.2 dependency source.'
    }
    Add-Type -AssemblyName System.IO.Compression
    $archive = [IO.Compression.ZipFile]::OpenRead($runtime)
    try {
        $dependencies = [ordered]@{
            'capstone.dll' = 'BepInEx/compatibility/python/Lib/site-packages/capstone/lib/capstone.dll'
            'dobby.dll' = 'BepInEx/core/dobby.dll'
            'Il2CppInterop.Common.dll' = 'BepInEx/core/Il2CppInterop.Common.dll'
        }
        foreach ($name in $dependencies.Keys) {
            $entry = $archive.GetEntry($dependencies[$name])
            if (-not $entry) { throw "Reviewed runtime is missing $name." }
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $scratch $name))
        }
    } finally { $archive.Dispose() }
    $capstoneDll = Join-Path $scratch 'capstone.dll'
    $dobbyDll = Join-Path $scratch 'dobby.dll'
    $commonDll = Join-Path $scratch 'Il2CppInterop.Common.dll'
} else {
    $capstoneRoot = Join-Path $scratch 'capstone'
    $dobbyRoot = Join-Path $scratch 'dobby'
    $commonRoot = Join-Path $scratch 'common'
    & (Join-Path $PSScriptRoot 'build-capstone.ps1') -BuildRoot $capstoneRoot | Out-Host
    & (Join-Path $PSScriptRoot 'build-dobby.ps1') -BuildRoot $dobbyRoot | Out-Host
    $capstone = Get-Content -LiteralPath (Join-Path $capstoneRoot 'build-provenance.json') -Raw | ConvertFrom-Json
    $dobby = Get-Content -LiteralPath (Join-Path $dobbyRoot 'build-provenance.json') -Raw | ConvertFrom-Json
    $commonZip = Join-Path $scratch 'Il2CppInterop-source.zip'
    Invoke-WebRequest -Uri 'https://codeload.github.com/BepInEx/Il2CppInterop/zip/dbda1cb353b0f4253345dc45136d170b9e50a5a0' -OutFile $commonZip
    & (Join-Path $PSScriptRoot 'build-il2cpp-common.ps1') -SourceZip $commonZip -BuildRoot $commonRoot | Out-Host
    $common = Get-Content -LiteralPath (Join-Path $commonRoot 'build-record.json') -Raw | ConvertFrom-Json
    $CapstoneIncludeDir = Join-Path $capstone.sourceRoot 'include'
    $capstoneDll = $capstone.dll
    $dobbyDll = $dobby.dll
    $commonDll = $common.candidate
}

& (Join-Path $PSScriptRoot 'build.ps1') -CapstoneIncludeDir $CapstoneIncludeDir | Out-Host
& (Join-Path $PSScriptRoot 'package.ps1') -Version $Version -Destination $Destination -CapstoneDll $capstoneDll -DobbyDll $dobbyDll -Il2CppCommonDll $commonDll
& (Join-Path $PSScriptRoot 'export-source.ps1') -Version $Version
