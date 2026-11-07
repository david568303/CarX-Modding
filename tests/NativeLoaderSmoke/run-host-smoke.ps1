param(
    [Parameter(Mandatory)][string]$Doorstop,
    [Parameter(Mandatory)][string]$Baseline,
    [Parameter(Mandatory)][string]$BuildRoot
)
$ErrorActionPreference='Stop'
$sourceRoot=$PSScriptRoot
$candidatePath=(Resolve-Path -LiteralPath $Doorstop).Path
$baselinePath=(Resolve-Path -LiteralPath $Baseline).Path
foreach($inputPath in @($candidatePath,$baselinePath)) {
    if(-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) { throw 'Doorstop and Baseline must identify existing DLL files.' }
}
$candidateHash=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
$baselineHash=(Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant()
$outputRoot=[IO.Path]::GetFullPath($BuildRoot)
if(Test-Path -LiteralPath $outputRoot) { throw 'BuildRoot must be a new directory. Existing files are never overwritten.' }
New-Item -ItemType Directory -Path $outputRoot -Force|Out-Null
$candidateRoot=Join-Path $outputRoot 'candidate'
$baselineRoot=Join-Path $outputRoot 'baseline'
New-Item -ItemType Directory -Path $candidateRoot,$baselineRoot -Force|Out-Null
$candidateCopy=Join-Path $candidateRoot 'winhttp.dll'
$baselineCopy=Join-Path $baselineRoot 'winhttp.dll'
Copy-Item -LiteralPath $candidatePath -Destination $candidateCopy
Copy-Item -LiteralPath $baselinePath -Destination $baselineCopy
Copy-Item -LiteralPath (Join-Path $sourceRoot 'disabled.ini') -Destination (Join-Path $outputRoot 'doorstop_config.ini')
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if(-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Existing Visual Studio tools are required; no compiler will be installed.' }
$vsRoot=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsRoot) { throw 'Existing Visual Studio x64 C++ tools were not found; no compiler will be installed.' }
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'|Out-Null
Push-Location $outputRoot
try {
    & cl.exe /nologo /W4 /O2 /MT /Fe:native_host_smoke.exe /Fo:native_host_smoke.obj (Join-Path $sourceRoot 'native_host_smoke.c')
    if($LASTEXITCODE -ne 0) { throw 'Native smoke host compilation failed.' }
    $hostOutput=& (Join-Path $outputRoot 'native_host_smoke.exe') $baselineCopy $candidateCopy
    if($LASTEXITCODE -ne 0) { throw 'Native forwarding/load/rebase smoke check failed.' }
    $result=($hostOutput -join "`n")|ConvertFrom-Json
    if(-not $result.success -or $result.checksPassed -ne 110) { throw 'Native smoke host did not report all 110 checks.' }
    if((Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateHash -or
       (Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $baselineHash -or
       (Get-FileHash -LiteralPath $candidateCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateHash -or
       (Get-FileHash -LiteralPath $baselineCopy -Algorithm SHA256).Hash.ToLowerInvariant() -ne $baselineHash) { throw 'An input or staged DLL changed during the test.' }
    [ordered]@{success=$true;candidateSha256=$candidateHash;baselineSha256=$baselineHash;checksPassed=$result.checksPassed;host=$result}|
        ConvertTo-Json -Depth 5|Tee-Object -FilePath (Join-Path $outputRoot 'forwarding-results.json')
} finally { Pop-Location }
