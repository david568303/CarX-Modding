param([string]$VisualStudioPath)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if(-not $VisualStudioPath) {
    $vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $VisualStudioPath=& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if(-not $VisualStudioPath) {throw 'Existing Visual Studio C++ build tools were not found.'}
$out=Join-Path $projectRoot '.work/tests/native'
New-Item -ItemType Directory -Force $out | Out-Null
Import-Module (Join-Path $VisualStudioPath 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $VisualStudioPath -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
Push-Location $out
try {
    & cl.exe /nologo /LD /W4 /O2 (Join-Path $PSScriptRoot 'runtime_fixture.c') /Fe:GameAssembly.dll /Fo:runtime_fixture.obj /link ("/DEF:"+(Join-Path $PSScriptRoot 'runtime_fixture.def')) /IMPLIB:fixture.lib /OPT:NOICF
    if($LASTEXITCODE -ne 0){throw 'Native test fixture build failed.'}
    & cl.exe /nologo /W4 /O2 (Join-Path $PSScriptRoot 'resolver_tests.c') (Join-Path $projectRoot 'src/Doorstop/src/windows/il2cpp_resolver.c') /Fe:resolver_tests.exe
    if($LASTEXITCODE -ne 0){throw 'Native resolver test build failed.'}
} finally { Pop-Location }
Copy-Item -LiteralPath (Join-Path $out 'GameAssembly.dll') -Destination (Join-Path $out 'OtherRuntime.dll') -Force
& (Join-Path $out 'resolver_tests.exe') | Tee-Object -FilePath (Join-Path $out 'results.txt')
if($LASTEXITCODE -ne 0){throw 'Native resolver tests failed.'}
