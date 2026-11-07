param(
    [Parameter(Mandatory = $true)]
    [string]$BuildRoot,
    [string]$SourceArchive,
    [string]$CMakePath
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$sourceCommit = '022575848782a4801fd150fdbc927effcbca0864'
$expectedSourceHash = 'eafc74835ab22d9745b29d4535c1723d6e0ddb79df840cf2f41125de9a441233'
$expectedPatchHash = '7a286bb090bf07bf113f42b0abfc273eeed96a20e50b3a48ea2ec48179e90907'
$expectedResourceHash = '14103cdb3967c5836dd0a9581a41122746afa71fea589e35a3637e8ccf5c7b74'
$expectedIntegrationHash = '3c4fa7ee9e07d3ecc97c6f07d24a15c520633f53f273d2c8ca644069554b0dd9'
$sourceUrl = "https://codeload.github.com/capstone-engine/capstone/zip/$sourceCommit"
$patchRelative = 'patches/capstone/5.0.9-initialize-encoding-size.patch'
$resourceRelative = 'patches/capstone/5.0.9-version.rc'
$integrationRelative = 'patches/capstone/5.0.9-msvc-provenance.cmake'
$patch = Join-Path $projectRoot $patchRelative
$resource = Join-Path $projectRoot $resourceRelative
$integration = Join-Path $projectRoot $integrationRelative

# Capstone and its LLVM-derived source retain their upstream BSD/LLVM notices.
# This build adds an output-initialization correctness fix, truthful Windows
# version/provenance resources and ordinary compiler security protections.
# No architecture, instruction metadata, syntax or allocator feature is removed.
$inputs = @(
    @{ Path = $patch; Hash = $expectedPatchHash },
    @{ Path = $resource; Hash = $expectedResourceHash },
    @{ Path = $integration; Hash = $expectedIntegrationHash }
)
foreach ($inputFile in $inputs) {
    if (-not (Test-Path -LiteralPath $inputFile.Path -PathType Leaf) -or
        (Get-FileHash -LiteralPath $inputFile.Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputFile.Hash) {
        throw "A pinned Capstone build input is missing or has changed: $($inputFile.Path)"
    }
}
if (-not $SourceArchive) {
    $SourceArchive = Join-Path $projectRoot ".work/downloads/capstone-$sourceCommit.zip"
}
$archivePath = [IO.Path]::GetFullPath($SourceArchive)
if (-not (Test-Path -LiteralPath $archivePath)) {
    New-Item -ItemType Directory -Path (Split-Path $archivePath -Parent) -Force | Out-Null
    $partial = $archivePath + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
    Invoke-WebRequest -Uri $sourceUrl -OutFile $partial
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSourceHash) {
        throw 'Downloaded Capstone source checksum mismatch; the archive was not accepted.'
    }
    Move-Item -LiteralPath $partial -Destination $archivePath
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf) -or
    (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSourceHash) {
    throw 'Pinned Capstone source archive checksum mismatch.'
}

$outputRoot = [IO.Path]::GetFullPath($BuildRoot)
if (Test-Path -LiteralPath $outputRoot) {
    $existing = Get-Item -LiteralPath $outputRoot -Force
    if (-not $existing.PSIsContainer -or
        ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        @(Get-ChildItem -LiteralPath $outputRoot -Force).Count -ne 0) {
        throw 'BuildRoot must be a new or empty ordinary directory; existing files are never overwritten.'
    }
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$sourceParent = Join-Path $outputRoot 'source'
Expand-Archive -LiteralPath $archivePath -DestinationPath $sourceParent
$sourceRoot = Join-Path $sourceParent "capstone-$sourceCommit"
foreach ($license in @('LICENSE.TXT', 'LICENSE_LLVM.TXT', 'bindings/python/LICENSE.TXT')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $license) -PathType Leaf)) {
        throw "The pinned source archive is missing its license notice: $license"
    }
}
$git = (Get-Command git.exe -ErrorAction Stop).Source
& $git -C $sourceRoot apply --check $patch
if ($LASTEXITCODE -ne 0) { throw 'Capstone correctness patch does not match the pinned source.' }
& $git -C $sourceRoot apply $patch
if ($LASTEXITCODE -ne 0) { throw 'Capstone correctness patch failed.' }
Copy-Item -LiteralPath $resource -Destination (Join-Path $sourceRoot 'capstone-version.rc')
Copy-Item -LiteralPath $integration -Destination (Join-Path $sourceRoot 'msvc-provenance.cmake')
[IO.File]::AppendAllText((Join-Path $sourceRoot 'CMakeLists.txt'),
    "`ninclude(`"`${CMAKE_CURRENT_LIST_DIR}/msvc-provenance.cmake`")`n", [Text.UTF8Encoding]::new($false))

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
    throw 'Existing Visual Studio C++ build tools are required. No compiler will be installed.'
}
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsRoot) { throw 'Existing Visual Studio C++ x64 tools were not found. No compiler will be installed.' }
$vsVersion = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion
Import-Module (Join-Path $vsRoot 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vsRoot -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64' | Out-Null
if (-not $CMakePath) { $CMakePath = (Get-Command cmake.exe -ErrorAction Stop).Source }
$cmake = (Get-Command $CMakePath -ErrorAction Stop).Source
$cmakeVersion = (& $cmake --version | Select-Object -First 1)
$nativeRoot = Join-Path $outputRoot 'native'

# Match the upstream Windows wheel recipe using the installed MSVC toolchain.
# The integration applies exactly the release's /GS, CFG, ASLR, DEP, high-entropy
# ASLR and CET-compatible flags. Ordinary PE link timestamps are retained;
# byte-identical output across build times/toolchains is not promised.
$configure = @('-S', $sourceRoot, '-B', $nativeRoot, '-G', 'NMake Makefiles',
    '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=ON', '-DBUILD_STATIC_LIBS=OFF',
    '-DBUILD_STATIC_RUNTIME=ON', '-DCAPSTONE_BUILD_TESTS=OFF', '-DCAPSTONE_BUILD_CSTOOL=OFF',
    '-DCAPSTONE_BUILD_CSTEST=OFF', '-DCAPSTONE_ARCHITECTURE_DEFAULT=ON',
    '-DCAPSTONE_BUILD_DIET=OFF', '-DCAPSTONE_X86_REDUCE=OFF', '-DCAPSTONE_X86_ATT_DISABLE=OFF',
    '-DCAPSTONE_USE_DEFAULT_ALLOC=ON', '-DCAPSTONE_DEBUG=OFF')
& $cmake @configure
if ($LASTEXITCODE -ne 0) { throw 'Capstone CMake configuration failed.' }
& $cmake --build $nativeRoot --target capstone_shared
if ($LASTEXITCODE -ne 0) { throw 'Capstone compilation failed.' }
$dll = Join-Path $nativeRoot 'capstone.dll'
if (-not (Test-Path -LiteralPath $dll -PathType Leaf)) { throw 'Compiled Capstone DLL was not produced.' }
$compilerFile = Get-ChildItem -LiteralPath (Join-Path $nativeRoot 'CMakeFiles') -Recurse -File -Filter 'CMakeCCompiler.cmake' | Select-Object -First 1
$compilerText = Get-Content -LiteralPath $compilerFile.FullName -Raw
$compilerId = [regex]::Match($compilerText, 'set\(CMAKE_C_COMPILER_ID "([^"]+)"\)').Groups[1].Value
$compilerVersion = [regex]::Match($compilerText, 'set\(CMAKE_C_COMPILER_VERSION "([^"]+)"\)').Groups[1].Value
if ($compilerId -ne 'MSVC') { throw 'The requested MSVC compiler was not selected.' }
$report = [ordered]@{
    format = 1
    component = 'Capstone'
    version = '5.0.9 + encoding-size initialization fix and Windows provenance/security integration'
    sourceCommit = $sourceCommit
    sourceUrl = $sourceUrl
    sourceArchiveSha256 = $expectedSourceHash
    sourcePatch = $patchRelative
    sourcePatchSha256 = $expectedPatchHash
    sourceResource = $resourceRelative
    sourceResourceSha256 = $expectedResourceHash
    sourceCMakeIntegration = $integrationRelative
    sourceCMakeIntegrationSha256 = $expectedIntegrationHash
    buildHelperSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    modifiedSourceSha256 = (Get-FileHash -LiteralPath (Join-Path $sourceRoot 'arch/X86/X86Mapping.c') -Algorithm SHA256).Hash.ToLowerInvariant()
    modifiedCMakeListsSha256 = (Get-FileHash -LiteralPath (Join-Path $sourceRoot 'CMakeLists.txt') -Algorithm SHA256).Hash.ToLowerInvariant()
    sourceRoot = $sourceRoot
    buildRoot = $nativeRoot
    dll = $dll
    dllBytes = (Get-Item -LiteralPath $dll).Length
    dllSha256 = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    compiler = $compilerId
    compilerVersion = $compilerVersion
    visualStudioVersion = [string]$vsVersion
    cmakeVersion = [string]$cmakeVersion
    configureArguments = $configure
    compilerMitigations = @('/GS', '/guard:cf')
    linkerMitigations = @('/guard:cf', '/DYNAMICBASE', '/NXCOMPAT', '/HIGHENTROPYVA', '/CETCOMPAT')
    recipeMatchesUpstreamWheelFeatures = $true
    byteIdenticalBuildsPromised = $false
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputRoot 'build-provenance.json') -Encoding utf8
$report | ConvertTo-Json -Depth 5
