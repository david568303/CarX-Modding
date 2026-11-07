param([Parameter(Mandatory)][string]$BuildRoot)
$ErrorActionPreference='Stop'
$BuildRoot=[IO.Path]::GetFullPath($BuildRoot)
if(Test-Path -LiteralPath $BuildRoot){throw 'Test BuildRoot must be a fresh directory.'}
New-Item -ItemType Directory -Path $BuildRoot | Out-Null
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsRoot=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if(-not $vsRoot){throw 'Existing Visual Studio x64 tools required; no installation attempted.'}
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
Push-Location $BuildRoot
try {
 & ml64.exe /nologo /c /Fofixture.obj (Join-Path $PSScriptRoot 'fixture.asm')
 if($LASTEXITCODE -ne 0){throw 'Fixture assembly failed.'}
 $exports=@('FixtureRipLoad','FixtureRipLea','FixtureRelativeCall','FixtureConditional','FixtureConditionalLong','FixtureInvokeFour','FixtureInteger','FixtureDouble','FixtureThunkRelative','FixtureThunkIndirect','FixturePreservedRegisters') | ForEach-Object { '/EXPORT:'+$_ }
 & link.exe /nologo /DLL /NOENTRY /OUT:fixture.dll /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /INCREMENTAL:NO fixture.obj @exports
 if($LASTEXITCODE -ne 0){throw 'Fixture linking failed.'}
 & cl.exe /nologo /std:c++17 /O2 /EHsc /MT /GS /guard:cf (Join-Path $PSScriptRoot 'native-host.cpp') /Fe:native-host.exe /link /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /guard:cf /INCREMENTAL:NO
 if($LASTEXITCODE -ne 0){throw 'Native test host build failed.'}
} finally {Pop-Location}
[ordered]@{visualStudio=$vsRoot;buildRoot=$BuildRoot;fixture=(Join-Path $BuildRoot 'fixture.dll');host=(Join-Path $BuildRoot 'native-host.exe')} | ConvertTo-Json
