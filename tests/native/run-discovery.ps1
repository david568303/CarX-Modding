param(
    [Parameter(Mandatory = $true)][string]$UnityPlayer,
    [Parameter(Mandatory = $true)][string]$GameAssembly,
    [Parameter(Mandatory = $true)][string]$ReferenceMap,
    [Parameter(Mandatory = $true)][string]$CapstoneIncludeDir,
    [Parameter(Mandatory = $true)][string]$CapstoneDll
)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$unityPath = (Resolve-Path -LiteralPath $UnityPlayer).Path
$gamePath = (Resolve-Path -LiteralPath $GameAssembly).Path
$reference = (Resolve-Path -LiteralPath $ReferenceMap).Path
$decoderPath = (Resolve-Path -LiteralPath $CapstoneDll).Path
$includePath = (Resolve-Path -LiteralPath $CapstoneIncludeDir).Path
$out = Join-Path $root ('.work/tests/native-discovery/' + [Guid]::NewGuid().ToString('N'))
$compatibility = Join-Path $out 'BepInEx/compatibility'
New-Item -ItemType Directory -Path $compatibility -Force | Out-Null
Copy-Item -LiteralPath $unityPath -Destination (Join-Path $out 'UnityPlayer.dll')
Copy-Item -LiteralPath $gamePath -Destination (Join-Path $out 'GameAssembly.dll')
Copy-Item -LiteralPath $decoderPath -Destination (Join-Path $compatibility 'capstone.dll')

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Existing Visual Studio C++ build tools were not found.' }
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
$native = Join-Path $root 'src/Doorstop/src/windows'
$sources = @('il2cpp_resolver.c', 'map_refresh.c', 'native_api_image.c',
             'native_api_discovery.c', 'native_api_semantics.c') |
    ForEach-Object { Join-Path $native $_ }
Push-Location $out
try {
    & cl.exe /nologo /W4 /O2 /MT /DDOORSTOP_NATIVE_API ('/I' + $includePath) (Join-Path $PSScriptRoot 'native_discovery_tests.c') @sources /Fe:native_discovery_tests.exe
    if ($LASTEXITCODE -ne 0) { throw 'Native discovery test build failed.' }

    function Invoke-DiscoveryTest([string]$Mode, [string]$ExpectedLog) {
        & .\native_discovery_tests.exe $Mode $reference
        if ($LASTEXITCODE -ne 0) { throw "Native discovery test failed: $Mode" }
        if ($ExpectedLog -and (Get-Content -Raw -LiteralPath 'BepInEx/cache/compatibility/api-refresh.log') -notmatch $ExpectedLog) {
            throw "Native discovery log did not match the expected outcome: $Mode"
        }
    }

    Invoke-DiscoveryTest cold 'Verified \d+ API bindings'
    $firstMap = (Get-FileHash -LiteralPath 'doorstop_api.ini').Hash
    Invoke-DiscoveryTest warm 'Verified \d+ API bindings'
    if ((Get-FileHash -LiteralPath 'doorstop_api.ini').Hash -ne $firstMap) { throw 'Warm discovery changed deterministic map output.' }
    Set-Content -LiteralPath 'doorstop_api.ini' -Value '[Target]', 'Format=2', 'Discovery=binary-loader-schema', 'TimeDateStamp=1', '[Exports]', 'il2cpp_init=Stale,1' -Encoding ascii
    Invoke-DiscoveryTest stale 'Verified \d+ API bindings'
    if ((Get-FileHash -LiteralPath 'doorstop_api.ini').Hash -ne $firstMap) { throw 'Stale output was not replaced with the verified map.' }
    Remove-Item -LiteralPath 'doorstop_api.ini'
    Invoke-DiscoveryTest swapped 'Native API discovery failed: il2cpp_init'
    Set-Content -LiteralPath 'doorstop_config.ini' -Value '[Compatibility]', 'auto_refresh=false' -Encoding ascii
    Invoke-DiscoveryTest disabled ''
    Remove-Item -LiteralPath 'doorstop_config.ini'
    Move-Item -LiteralPath 'BepInEx/compatibility/capstone.dll' -Destination 'BepInEx/compatibility/capstone.disabled'
    try {
        Invoke-DiscoveryTest missing-decoder 'could not load the packaged x64 Capstone 5 decoder'
    } finally {
        Move-Item -LiteralPath 'BepInEx/compatibility/capstone.disabled' -Destination 'BepInEx/compatibility/capstone.dll'
    }
} finally { Pop-Location }
Write-Host "Native discovery test scratch directory $out"
