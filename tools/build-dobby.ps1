param(
    [Parameter(Mandatory = $true)]
    [string]$BuildRoot,
    [string]$SourceArchive,
    [string]$CMakePath
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$sourceCommit = '888d971214900374edbca6206fad6ded8a2c1311'
$sourceUrl = "https://codeload.github.com/BepInEx/Dobby/zip/$sourceCommit"
$expectedSourceHash = '00c0a582fc69efd52aa3a95449d27882384b653eb0e6524b79e796e8a8ef807d'
$resourceRelative = 'patches/dobby/1.0.5-version.rc'
$integrationRelative = 'patches/dobby/1.0.5-msvc-provenance.cmake'
$expectedResourceHash = 'fd681551c72c1cbb19c4d09b3f3d6e193ab2c3fa1061ca1d212415edc893cb33'
$expectedIntegrationHash = 'c2f7e62f87d4210c9fe55e01c442cf79bed66f6074b7cc30ff7da77b8f813c60'
$resource = Join-Path $projectRoot $resourceRelative
$integration = Join-Path $projectRoot $integrationRelative
$outputRoot = [IO.Path]::GetFullPath($BuildRoot)
$longInclude = Join-Path $outputRoot "source/Dobby-$sourceCommit/source/InstructionRelocation/x86/x86_insn_decode/x86_opcode_modrm_reg_group.c"
if ($longInclude.Length -ge 260) { throw 'BuildRoot is too long for MSVC source includes; choose a shorter isolated directory.' }
if (Test-Path -LiteralPath $outputRoot) {
    $existing = Get-Item -LiteralPath $outputRoot -Force
    if (-not $existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        @(Get-ChildItem -LiteralPath $outputRoot -Force).Count -ne 0) {
        throw 'BuildRoot must be a new or empty ordinary directory; existing files are never overwritten.'
    }
}
foreach ($inputFile in @(@{ Path=$resource; Hash=$expectedResourceHash },@{ Path=$integration; Hash=$expectedIntegrationHash })) {
    if (-not (Test-Path -LiteralPath $inputFile.Path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $inputFile.Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputFile.Hash) {
        throw "A pinned Dobby build input is missing or changed: $($inputFile.Path)"
    }
}
if (-not $SourceArchive) { $SourceArchive = Join-Path $projectRoot ".work/downloads/Dobby-$sourceCommit.zip" }
$archivePath = [IO.Path]::GetFullPath($SourceArchive)
if (-not (Test-Path -LiteralPath $archivePath)) {
    New-Item -ItemType Directory -Path (Split-Path $archivePath -Parent) -Force | Out-Null
    $partial = $archivePath + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
    Invoke-WebRequest -Uri $sourceUrl -OutFile $partial
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSourceHash) {
        throw 'Downloaded Dobby archive checksum mismatch; the archive was not accepted.'
    }
    Move-Item -LiteralPath $partial -Destination $archivePath
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf) -or
    (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSourceHash) {
    throw 'Pinned Dobby source archive checksum mismatch.'
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$sourceParent = Join-Path $outputRoot 'source'
Expand-Archive -LiteralPath $archivePath -DestinationPath $sourceParent
$sourceRoot = Join-Path $sourceParent "Dobby-$sourceCommit"
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'LICENSE') -PathType Leaf)) { throw 'Source license is missing.' }
if (Test-Path -LiteralPath (Join-Path $sourceRoot '.git')) { throw 'The pinned source archive must not contain Git metadata.' }
Copy-Item -LiteralPath $resource -Destination (Join-Path $sourceRoot 'dobby-version.rc')
Copy-Item -LiteralPath $integration -Destination (Join-Path $sourceRoot 'msvc-provenance.cmake')
[IO.File]::AppendAllText((Join-Path $sourceRoot 'CMakeLists.txt'),
    "`ninclude(`"`${CMAKE_CURRENT_LIST_DIR}/msvc-provenance.cmake`")`n", [Text.UTF8Encoding]::new($false))

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Existing Visual Studio C++ tools are required. No compiler will be installed.' }
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Existing Visual Studio C++ x64 tools were not found. No compiler will be installed.' }
$vsVersion = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
if (-not $CMakePath) { $CMakePath = (Get-Command cmake.exe -ErrorAction Stop).Source }
$cmake = (Get-Command $CMakePath -ErrorAction Stop).Source
$nativeRoot = Join-Path $outputRoot 'native'

# Preserve the official Windows release's features and normal static CRT startup.
# The integration adds the recorded resource and ordinary compiler protections.
$configure = @('-S', $sourceRoot, '-B', $nativeRoot, '-G', 'NMake Makefiles',
    '-DCMAKE_SYSTEM_NAME=Windows', '-DCMAKE_SYSTEM_PROCESSOR=amd64',
    '-DCMAKE_BUILD_TYPE=Release', '-DDOBBY_GENERATE_SHARED=ON', '-DDOBBY_DEBUG=OFF',
    '-DDynamicBinaryInstrument=OFF', '-DPlugin.SymbolResolver=OFF', '-DNearBranch=ON',
    '-DFullFloatingPointRegisterPack=OFF', '-DEnableObfuscation=OFF')

# Upstream only queries git when source/.git exists. Also bound discovery during
# the build so extracting under a parent checkout cannot supply its commit ID.
$previousGitCeiling = [Environment]::GetEnvironmentVariable('GIT_CEILING_DIRECTORIES','Process')
try {
    [Environment]::SetEnvironmentVariable('GIT_CEILING_DIRECTORIES',$sourceRoot,'Process')
    & $cmake @configure
    if ($LASTEXITCODE -ne 0) { throw 'Dobby CMake configuration failed.' }
    & $cmake --build $nativeRoot --target dobby
    if ($LASTEXITCODE -ne 0) { throw 'Dobby compilation failed.' }
} finally {
    [Environment]::SetEnvironmentVariable('GIT_CEILING_DIRECTORIES',$previousGitCeiling,'Process')
}
$dll = Join-Path $nativeRoot 'dobby.dll'
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw 'Compiled Dobby DLL was not produced.' }
$compilerFile = Get-ChildItem -LiteralPath (Join-Path $nativeRoot 'CMakeFiles') -File -Recurse -Filter 'CMakeCXXCompiler.cmake' | Select-Object -First 1
$compilerText = Get-Content -LiteralPath $compilerFile.FullName -Raw
$compilerId = [regex]::Match($compilerText,'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)').Groups[1].Value
if ($compilerId -ne 'MSVC') { throw 'The requested MSVC compiler was not selected.' }
$compiler = (Get-Command cl.exe).Source
$sourceFiles = Get-ChildItem -LiteralPath $sourceRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
    [ordered]@{ path=$_.FullName.Substring($sourceRoot.Length+1).Replace('\','/');
        sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$sourceManifest = Join-Path $outputRoot 'source-file-hashes.json'
$sourceFiles | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $sourceManifest -Encoding UTF8
$toolRecords = foreach ($tool in @('cl.exe','link.exe','nmake.exe','rc.exe',$cmake)) {
    $path = (Get-Command $tool -ErrorAction Stop).Source
    $item = Get-Item -LiteralPath $path
    [ordered]@{ name=$item.Name; path=$item.FullName; version=$item.VersionInfo.FileVersion;
        sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$report = [ordered]@{
    format=1; component='Dobby (BepInEx fork)'; version='1.0.5'
    sourceCommit=$sourceCommit; sourceUrl=$sourceUrl; sourceArchiveSha256=$expectedSourceHash
    sourceResource=$resourceRelative; sourceResourceSha256=$expectedResourceHash
    sourceCMakeIntegration=$integrationRelative; sourceCMakeIntegrationSha256=$expectedIntegrationHash
    upstreamLicenseSha256=(Get-FileHash -LiteralPath (Join-Path $sourceRoot 'LICENSE') -Algorithm SHA256).Hash.ToLowerInvariant()
    modifiedCMakeListsSha256=(Get-FileHash -LiteralPath (Join-Path $sourceRoot 'CMakeLists.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
    buildHelperSha256=(Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    sourceFilesManifestSha256=(Get-FileHash -LiteralPath $sourceManifest -Algorithm SHA256).Hash.ToLowerInvariant()
    sourceFileCount=@($sourceFiles).Count; sourceRoot=$sourceRoot; buildRoot=$nativeRoot
    runtimeSourceModified=$false; featureProfileMatchesOfficialWindowsRelease=$true
    compiler=$compilerId; compilerVersion=(Get-Item -LiteralPath $compiler).VersionInfo.FileVersion
    visualStudioVersion=[string]$vsVersion; cmakeVersion=[string](& $cmake --version | Select-Object -First 1)
    tools=@($toolRecords); configureArguments=$configure
    compilerMitigations=@('/GS','/guard:cf')
    linkerMitigations=@('/guard:cf','/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA')
    cetCompatibilityClaimed=$false; archiveGitMetadataAbsent=$true; gitDiscoveryCeilingScopedAndRestored=$true
    dll=$dll; dllBytes=(Get-Item -LiteralPath $dll).Length
    dllSha256=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    byteIdenticalBuildsPromised=$false
}
$report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $outputRoot 'build-provenance.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 7
