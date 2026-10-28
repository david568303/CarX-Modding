$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$downloadRoot = Join-Path $projectRoot '.work/downloads'
$runtimeRoot = Join-Path $projectRoot '.work/vendor/BepInEx'
$archive = Join-Path $downloadRoot 'BepInEx-Unity.IL2CPP-win-x64-6.0.0-be.791+b782da4.zip'
$expectedHash = 'bb1c510909b69522733791f3a0817a487379a52da6468a492f1c9c19b3ec6f9a'
New-Item -ItemType Directory -Path $downloadRoot,$runtimeRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $archive)) {
    Invoke-WebRequest -Uri 'https://builds.bepinex.dev/projects/bepinex_be/791/BepInEx-Unity.IL2CPP-win-x64-6.0.0-be.791%2Bb782da4.zip' -OutFile $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'The pinned official BepInEx archive checksum does not match.'
}
Expand-Archive -LiteralPath $archive -DestinationPath $runtimeRoot -Force
if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'BepInEx/core/BepInEx.Unity.IL2CPP.dll')) -or
    -not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'dotnet/coreclr.dll'))) {
    throw 'The pinned BepInEx archive is missing its IL2CPP loader or portable runtime.'
}
Write-Output $runtimeRoot
