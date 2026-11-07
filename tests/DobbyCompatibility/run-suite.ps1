[CmdletBinding()]
param(
 [Parameter(Mandatory)][string]$Baseline,
 [Parameter(Mandatory)][string]$Candidate,
 [Parameter(Mandatory)][string]$RuntimeRoot,
 [Parameter(Mandatory)][string]$BuildRoot,
 [string]$DotnetExecutable,
 [string]$PythonExecutable
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7){throw 'Use existing PowerShell 7; no tools are installed by this suite.'}
$Baseline=(Resolve-Path -LiteralPath $Baseline).Path
$Candidate=(Resolve-Path -LiteralPath $Candidate).Path
$RuntimeRoot=(Resolve-Path -LiteralPath $RuntimeRoot).Path
$BuildRoot=[IO.Path]::GetFullPath($BuildRoot)
if(Test-Path -LiteralPath $BuildRoot){throw 'BuildRoot must be a fresh directory.'}
if($BuildRoot.StartsWith($RuntimeRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){
 throw 'BuildRoot must be outside the input runtime.'
}
foreach($name in @('GameAssembly.dll','UnityPlayer.dll')){
 if(Test-Path -LiteralPath (Join-Path $RuntimeRoot $name)){throw 'RuntimeRoot must be an isolated extracted loader ZIP, not a game directory.'}
}
$core=Join-Path $RuntimeRoot 'BepInEx/core'
$runtimeDotnet=Join-Path $RuntimeRoot 'dotnet'
foreach($name in @('BepInEx.Core.dll','BepInEx.Unity.IL2CPP.dll')){
 if(-not(Test-Path -LiteralPath (Join-Path $core $name) -PathType Leaf)){throw "Required shipped assembly is missing: $name"}
}
if(-not(Test-Path -LiteralPath (Join-Path $runtimeDotnet 'coreclr.dll') -PathType Leaf)){throw 'Bundled CoreCLR input is missing.'}
if(-not $PythonExecutable){$PythonExecutable=Join-Path $RuntimeRoot 'BepInEx/compatibility/python/python.exe'}
$PythonExecutable=(Resolve-Path -LiteralPath $PythonExecutable).Path
if(-not $DotnetExecutable){$DotnetExecutable=(Get-Command dotnet.exe -ErrorAction Stop).Source}
$DotnetExecutable=(Resolve-Path -LiteralPath $DotnetExecutable).Path
$installedRoot=Split-Path $DotnetExecutable -Parent
$fxrRoot=Join-Path $installedRoot 'host/fxr'
$fxr=Get-ChildItem -LiteralPath $fxrRoot -Directory | Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
if(-not $fxr -or -not(Test-Path -LiteralPath (Join-Path $fxr.FullName 'hostfxr.dll'))){throw 'An existing dotnet host and hostfxr are required; nothing will be installed.'}
New-Item -ItemType Directory -Path $BuildRoot | Out-Null
& $PythonExecutable -B (Join-Path $PSScriptRoot 'compare-results.py') snapshot --runtime-root $RuntimeRoot --build-root $BuildRoot
if($LASTEXITCODE -ne 0){throw 'Input runtime inventory failed.'}

# A private portable layout uses the existing host and the actual input runtime.
# No SDK/runtime is installed, downloaded or substituted for the supplied CoreCLR.
$portableRoot=Join-Path $BuildRoot 'portable-dotnet'
$privateFxr=Join-Path $portableRoot ('host/fxr/'+$fxr.Name)
$privateRuntime=Join-Path $portableRoot 'shared/Microsoft.NETCore.App/6.0.7'
New-Item -ItemType Directory -Path $privateFxr,$privateRuntime -Force | Out-Null
Copy-Item -LiteralPath $DotnetExecutable -Destination (Join-Path $portableRoot 'dotnet.exe')
Copy-Item -LiteralPath (Join-Path $fxr.FullName 'hostfxr.dll') -Destination $privateFxr
foreach($file in Get-ChildItem -LiteralPath $runtimeDotnet -Force){
 if($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Bundled runtime must contain ordinary files.'}
 Copy-Item -LiteralPath $file.FullName -Destination $privateRuntime
}
$sdk=& $DotnetExecutable --version
if($LASTEXITCODE -ne 0){throw 'Existing .NET SDK unavailable; no compiler will be installed.'}
$nativeBuild=Join-Path $BuildRoot 'native-build'
& (Join-Path $PSScriptRoot 'build-tests.ps1') -BuildRoot $nativeBuild
if($LASTEXITCODE -ne 0){throw 'Native fixture/host build failed.'}
$managedBuild=Join-Path $BuildRoot 'managed-build'
$managedObj=Join-Path $BuildRoot 'managed-obj'
$objWithSeparator=$managedObj+[IO.Path]::DirectorySeparatorChar
& $DotnetExecutable build (Join-Path $PSScriptRoot 'managed/ManagedDobbyAudit.csproj') -c Release --nologo -p:ImportDirectoryBuildProps=false -p:ImportDirectoryBuildTargets=false ("-p:BaseIntermediateOutputPath=$objWithSeparator") ("-p:MSBuildProjectExtensionsPath=$objWithSeparator") -o $managedBuild
if($LASTEXITCODE -ne 0){throw 'Managed audit build failed.'}
[ordered]@{baseline=$Baseline;candidate=$Candidate;runtimeRoot=$RuntimeRoot;sdk=[string]$sdk;existingDotnetHost=$DotnetExecutable;existingHostFxr=$fxr.FullName;runtimeSource=$runtimeDotnet;installedAnything=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BuildRoot 'toolchain.json') -Encoding utf8
$fixture=Join-Path $nativeBuild 'fixture.dll'
& $PythonExecutable -B (Join-Path $PSScriptRoot 'run-native.py') --baseline $Baseline --candidate $Candidate --build-root $nativeBuild --output-dir (Join-Path $BuildRoot 'native-results')
$nativeExit=$LASTEXITCODE
& $PythonExecutable -B (Join-Path $PSScriptRoot 'run-managed.py') --baseline $Baseline --candidate $Candidate --core $core --fixture $fixture --app (Join-Path $managedBuild 'ManagedDobbyAudit.dll') --dotnet (Join-Path $portableRoot 'dotnet.exe') --output-dir (Join-Path $BuildRoot 'managed-results')
$managedExit=$LASTEXITCODE
& $PythonExecutable -B (Join-Path $PSScriptRoot 'probe-jcc.py') --library $Baseline --fixture $fixture --output (Join-Path $BuildRoot 'jcc-baseline.json')
if($LASTEXITCODE -ne 0){throw 'Baseline Jcc diagnostic process failed.'}
& $PythonExecutable -B (Join-Path $PSScriptRoot 'probe-jcc.py') --library $Candidate --fixture $fixture --output (Join-Path $BuildRoot 'jcc-candidate.json')
if($LASTEXITCODE -ne 0){throw 'Candidate Jcc diagnostic process failed.'}
& $PythonExecutable -B (Join-Path $PSScriptRoot 'compare-results.py') compare --runtime-root $RuntimeRoot --build-root $BuildRoot
$comparisonExit=$LASTEXITCODE
Write-Host "Native test exit: $nativeExit; managed test exit: $managedExit; comparison exit: $comparisonExit"
Write-Host (Join-Path $BuildRoot 'comparison.json')
if($nativeExit -ne 0 -or $managedExit -ne 0 -or $comparisonExit -ne 0){exit 1}
exit 0
