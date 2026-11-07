param(
    [Parameter(Mandatory)][string]$Doorstop,
    [Parameter(Mandatory)][string]$BuildRoot
)
$ErrorActionPreference='Stop'
$sourceRoot=$PSScriptRoot
$candidatePath=(Resolve-Path -LiteralPath $Doorstop).Path
if(-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { throw 'Doorstop must identify an existing DLL file.' }
$candidateHash=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
$outputRoot=[IO.Path]::GetFullPath($BuildRoot)
if(Test-Path -LiteralPath $outputRoot) { throw 'BuildRoot must be a new directory. Existing files are never overwritten.' }
New-Item -ItemType Directory -Path $outputRoot -Force|Out-Null
$loaderRoot=Join-Path $outputRoot 'loader'
New-Item -ItemType Directory -Path $loaderRoot -Force|Out-Null
$candidateCopy=Join-Path $loaderRoot 'winhttp.dll'
Copy-Item -LiteralPath $candidatePath -Destination $candidateCopy
Copy-Item -LiteralPath (Join-Path $sourceRoot 'enabled.ini') -Destination (Join-Path $outputRoot 'doorstop_config.ini')
'Inert file: never loaded as managed code.'|Set-Content -LiteralPath (Join-Path $outputRoot 'inert-target.txt') -Encoding ascii
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if(-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Existing Visual Studio tools are required; no compiler will be installed.' }
$vsRoot=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsRoot) { throw 'Existing Visual Studio x64 C++ tools were not found; no compiler will be installed.' }
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'|Out-Null
Push-Location $outputRoot
try {
    $definition='/DEF:'+(Join-Path $sourceRoot 'fake_gameassembly.def')
    & cl.exe /nologo /W4 /O2 /MT /LD /Fe:GameAssembly.dll /Fo:fake_gameassembly.obj (Join-Path $sourceRoot 'fake_gameassembly.c') /link $definition
    if($LASTEXITCODE -ne 0) { throw 'Synthetic GameAssembly fixture compilation failed.' }
    & cl.exe /nologo /W4 /O2 /MT /Fe:enabled_hook_host.exe /Fo:enabled_hook_host.obj (Join-Path $sourceRoot 'enabled_hook_host.c')
    if($LASTEXITCODE -ne 0) { throw 'Enabled native smoke host compilation failed.' }
    $hostOutput=& (Join-Path $outputRoot 'enabled_hook_host.exe') $candidateCopy
    if($LASTEXITCODE -ne 0) { throw 'Enabled loader IAT smoke check failed.' }
    $result=($hostOutput -join "`n")|ConvertFrom-Json
    if(-not $result.success -or $result.checksPassed -ne 59 -or
       -not $result.canonicalInitWrapped -or -not $result.forgedMapIgnored -or
       $result.coreclrLoaded -or $result.discoveryEntered -or $result.runtimeCalls -ne 0) {
        throw 'Enabled smoke host did not report the complete isolated 59-check result.'
    }
    if((Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateHash -or
       (Get-FileHash -LiteralPath $candidateCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateHash) { throw 'Input or staged loader DLL changed during the test.' }
    [ordered]@{success=$true;candidateSha256=$candidateHash;checksPassed=$result.checksPassed;host=$result}|
        ConvertTo-Json -Depth 5|Tee-Object -FilePath (Join-Path $outputRoot 'enabled-results.json')
} finally { Pop-Location }
