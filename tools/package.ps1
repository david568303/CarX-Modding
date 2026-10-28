param(
    [switch]$StageOnly,
    [string]$Destination
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'package-licenses.ps1')
$portablePython = Join-Path $projectRoot '.work/vendor/python-embed/python.exe'
if (-not (Test-Path -LiteralPath $portablePython)) { & (Join-Path $PSScriptRoot 'prepare-python.ps1') }
& $portablePython -B (Join-Path $PSScriptRoot 'prepare-licenses.py')
if ($LASTEXITCODE -ne 0) { throw 'Pinned licenses or corresponding upstream source verification failed.' }
$workRoot = Join-Path $projectRoot '.work/package'
$releaseRoot = Join-Path $projectRoot 'release'
New-Item -ItemType Directory -Path $workRoot,$releaseRoot -Force | Out-Null
if (-not $Destination) { $Destination = Join-Path $releaseRoot 'BepInEx-Doorstop-NoPDB.zip' }
$zipPath = [IO.Path]::GetFullPath($Destination)
if ([IO.Path]::GetExtension($zipPath) -ne '.zip') { throw 'Destination must be a ZIP file.' }
New-Item -ItemType Directory -Path (Split-Path $zipPath -Parent) -Force | Out-Null
$stageRoot = Join-Path $workRoot ('stage-' + [Guid]::NewGuid().ToString('N'))
$sourceStage = Join-Path $workRoot ('source-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stageRoot,$sourceStage -Force | Out-Null

function Copy-Into([string]$Source, [string]$Base, [string]$RelativePath) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Required package input is missing: $Source" }
    $target = [IO.Path]::GetFullPath((Join-Path $Base $RelativePath))
    if (-not $target.StartsWith($Base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A package destination escaped its staging directory.'
    }
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $target -Force
}

function Copy-Tree([string]$Source, [string]$Base, [string]$RelativePath, [switch]$SourceOnly) {
    $treeRoot = (Resolve-Path -LiteralPath $Source).Path
    foreach ($entry in Get-ChildItem -LiteralPath $treeRoot -Recurse -Force) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "A package source contains a link: $($entry.FullName)" }
        if ($entry.PSIsContainer) { continue }
        $relative = [IO.Path]::GetRelativePath($treeRoot, $entry.FullName)
        if ($relative -match '(^|[\\/])(__pycache__|\.git)([\\/]|$)' -or $entry.Extension -eq '.pyc') { continue }
        if ($entry.Name -match '^pdbsymbols\.') { continue }
        if ($SourceOnly -and ($relative -match '(^|[\\/])(bin|obj)([\\/]|$)' -or $entry.Extension -in @('.obj','.pdb','.exe','.dll'))) { continue }
        Copy-Into $entry.FullName $Base (Join-Path $RelativePath $relative)
    }
}

function Write-Zip([string]$Base, [string]$Output, [string[]]$EmptyDirectories = @()) {
    Add-Type -AssemblyName System.IO.Compression
    $stream = [IO.File]::Open($Output, [IO.FileMode]::Create, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
        try {
            foreach ($directory in $EmptyDirectories) { $archive.CreateEntry($directory.TrimEnd('/') + '/') | Out-Null }
            foreach ($entry in Get-ChildItem -LiteralPath $Base -Recurse -File -Force) {
                $relative = [IO.Path]::GetRelativePath($Base, $entry.FullName).Replace('\','/')
                if ($relative.StartsWith('/') -or $relative -match '(^|/)\.\.(/|$)|^[A-Za-z]:|\\') { throw "Unsafe ZIP path: $relative" }
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $entry.FullName, $relative, [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        } finally { $archive.Dispose() }
    } finally { $stream.Dispose() }
}

function Get-SourceRevision([string]$Directory) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $null }
    $top = & git -C $Directory rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath([string]$top) -ine [IO.Path]::GetFullPath($Directory)) { return $null }
    $commit = & git -C $Directory rev-parse --verify HEAD 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]$commit -notmatch '^[0-9a-f]{40}$') { return $null }
    $status = & git -C $Directory status --porcelain
    return [ordered]@{commit=[string]$commit; dirty=([bool]$status)}
}

$officialPackage = Join-Path $projectRoot '.work/vendor/BepInEx'
if (-not (Test-Path -LiteralPath (Join-Path $officialPackage 'BepInEx/core/BepInEx.Unity.IL2CPP.dll'))) {
    & (Join-Path $PSScriptRoot 'prepare-bepinex.ps1')
}
Copy-Tree (Join-Path $officialPackage 'BepInEx/core') $stageRoot 'BepInEx/core'
Copy-Tree (Join-Path $officialPackage 'dotnet') $stageRoot 'dotnet'
Copy-Tree (Join-Path $projectRoot '.work/vendor/python-embed') $stageRoot 'BepInEx/compatibility/python'
foreach ($name in @('winhttp.dll','.doorstop_version')) {
    Copy-Into (Join-Path $projectRoot ".work/build/doorstop-x64/$name") $stageRoot $name
}
Copy-Into (Join-Path $projectRoot '.work/build/MetadataBootstrap/Release/net6.0/BepInEx.MetadataBootstrap.dll') $stageRoot 'BepInEx/core/BepInEx.MetadataBootstrap.dll'
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src/ApiResolver') -File | Where-Object { $_.Extension -in @('.py','.json') -or $_.Name -eq 'requirements.txt' }) {
    if ($file.Extension -eq '.py' -and (Get-Content -LiteralPath $file.FullName -Raw) -match 'symbolserver\.unity3d\.com|(?:read_pdb_identity|validate_pdb_identity|obtain_pdb)\s*\(|pdbsymbols\.exe|msdia140\.dll') {
        throw "An obsolete debug-symbol dependency remains in API discovery: $($file.Name)"
    }
    Copy-Into $file.FullName $stageRoot ("BepInEx/compatibility/tools/" + $file.Name)
}
foreach ($name in @('normalize_metadata.py','infer_native_decoder.py','requirements.txt')) {
    Copy-Into (Join-Path $projectRoot "src/MetadataNormalizer/$name") $stageRoot "BepInEx/core/scripts/$name"
}
New-Item -ItemType Directory -Path (Join-Path $stageRoot 'BepInEx/plugins'),(Join-Path $stageRoot 'BepInEx/patchers') -Force | Out-Null

@'
[General]
enabled=true
target_assembly=BepInEx\core\BepInEx.MetadataBootstrap.dll
redirect_output_log=false
ignore_disable_switch=true

[Il2Cpp]
coreclr_path=dotnet\coreclr.dll
corlib_dir=dotnet

[Compatibility]
auto_refresh=true
helper_script=BepInEx\compatibility\tools\prepare_api_map.py
python_executable=BepInEx\compatibility\python\python.exe
'@ | Set-Content -LiteralPath (Join-Path $stageRoot 'doorstop_config.ini') -Encoding ascii

@'
Extract this ZIP's contents directly beside CarX Drift Racing Online 2.exe,
then launch the game normally through Steam. No separate launcher is needed.

The first launch discovers API bindings directly from the paired game binaries,
normalizes the game's metadata, and generates BepInEx interop assemblies. This
can take a few minutes. BepInEx may download Unity base libraries when needed;
API discovery does not download debug symbols. Later launches reuse caches
after verifying the game inputs.

Install plugins made for BepInEx 6 and Unity IL2CPP in BepInEx\plugins.
The package does not include a demonstration or verification plugin.
Loader results appear in BepInEx\LogOutput.log and BepInEx\metadata-bootstrap.log.

The package includes Python and CoreCLR runtimes. It installs no compiler or
system runtime. Runtime discovery requires no PDB files, DIA SDK, or Visual Studio.
The metadata normalizer currently supports recognized metadata 38/39 layouts;
unrecognized future formats are refused rather than guessed.

No original game executable, UnityPlayer, GameAssembly, original metadata,
save files, generated interop assemblies, or old debug-symbol caches are in
this ZIP. Generated compatibility files stay under BepInEx and the game's
Doorstop configuration. Existing mod-loader files may be replaced on extraction.

Corresponding modified source and build instructions:
  BepInEx\compatibility\source.zip
Unmodified upstream corresponding source archives:
  BepInEx\compatibility\sources
Licenses and component notices:
  LICENSE, THIRD-PARTY-NOTICES.md, licenses
'@ | Set-Content -LiteralPath (Join-Path $stageRoot 'README.txt') -Encoding ascii

# Include all corresponding modified source, without test/build/cache outputs.
foreach ($directory in @('Doorstop','ApiResolver','MetadataNormalizer','MetadataBootstrap')) {
    Copy-Tree (Join-Path $projectRoot "src/$directory") $sourceStage "src/$directory" -SourceOnly
}
Copy-Into (Join-Path $projectRoot 'Directory.Build.props') $sourceStage 'Directory.Build.props'
foreach ($name in @('build-doorstop.ps1','prepare-python.ps1','prepare-bepinex.ps1','build.ps1','prepare-licenses.py')) {
    Copy-Into (Join-Path $projectRoot "tools/$name") $sourceStage "tools/$name"
}
foreach ($item in Get-PackageLicenseFiles $projectRoot) {
    Copy-Into (Join-Path $projectRoot $item.Source) $stageRoot $item.Entry
    Copy-Into (Join-Path $projectRoot $item.Source) $sourceStage $item.Entry
}
$vendorSources = Join-Path $projectRoot '.work/vendor-sources'
if (-not (Test-Path -LiteralPath $vendorSources -PathType Container) -or
    @((Get-ChildItem -LiteralPath $vendorSources -File) | Where-Object Name -Match 'BepInEx').Count -eq 0 -or
    @((Get-ChildItem -LiteralPath $vendorSources -File) | Where-Object Name -Match 'Il2CppInterop').Count -eq 0) {
    throw 'Required upstream corresponding source archives are missing. Run the bundled Python with tools/prepare-licenses.py first.'
}
Copy-Tree $vendorSources $stageRoot 'BepInEx/compatibility/sources'
@'
Corresponding source for the bundled Doorstop/API/metadata compatibility layer.
No game binaries or generated game metadata are included.

With the already installed Visual Studio C++ tools and .NET SDK, run from here:
  .\tools\build-doorstop.ps1
  dotnet build .\src\MetadataBootstrap\MetadataBootstrap.csproj -c Release

Outputs are placed under .work\build. To use your rebuilt files while the game
is closed, replace the game's winhttp.dll and BepInEx\core\BepInEx.MetadataBootstrap.dll
with the corresponding outputs.
Python sources are used directly: ApiResolver files belong in
BepInEx\compatibility\tools; MetadataNormalizer Python files belong in
BepInEx\core\scripts. The build scripts do not install a compiler.

The portable Python preparation script downloads the pinned official runtime
and pinned pefile/capstone wheels and checks their SHA-256 values. No host
Python packages or compiler downloads are used. The application ZIP already
includes this runtime. prepare-bepinex.ps1 obtains the pinned official loader.

UnityDoorstop is licensed under LGPL 2.1. Its license and original notices
are in src\Doorstop\LICENSE. The modified Doorstop source is complete here.
The remaining upstream BepInEx/runtime components are supplied unmodified.
See THIRD-PARTY-NOTICES.md and licenses for component terms. Exact upstream
source archives are alongside this ZIP in BepInEx/compatibility/sources.
'@ | Set-Content -LiteralPath (Join-Path $sourceStage 'BUILD.txt') -Encoding ascii
$sourceZip = Join-Path $stageRoot 'BepInEx/compatibility/source.zip'
Write-Zip $sourceStage $sourceZip
Copy-Into (Join-Path $projectRoot 'src/Doorstop/LICENSE') $stageRoot 'BepInEx/compatibility/licenses/UnityDoorstop-LGPL.txt'

$manifest = foreach ($entry in Get-ChildItem -LiteralPath $stageRoot -Recurse -File -Force) {
    $relative = [IO.Path]::GetRelativePath($stageRoot, $entry.FullName).Replace('\','/')
    if ($relative -match '(?i)(^|/)(GameAssembly\.dll|UnityPlayer\.dll|CarX Drift Racing Online 2\.exe|global-metadata\.dat|Verification\.dll|CarX\.BepInEx\.Verification\.dll|doorstop_api\.ini)$') {
        throw "A game input, precomputed map, or test plugin entered the package: $relative"
    }
    if ($relative -match '(?i)(^|/)(pdbsymbols\.[^/]+|msdia[^/]*)$') {
        throw "An obsolete debug-symbol helper entered the package: $relative"
    }
    if ($relative -match '(?i)(^|/)(interop|unity-libs|__pycache__|downloads|cache)(/|$)' -or $relative -match '(?i)\.(pdb|log|pyc)$') {
        throw "A generated cache, log, or PDB entered the package: $relative"
    }
    [ordered]@{path=$relative; length=$entry.Length; sha256=(Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{format=1; createdUtc=[DateTime]::UtcNow.ToString('o'); sourceRevision=(Get-SourceRevision $projectRoot); doorstopRevision=(Get-SourceRevision (Join-Path $projectRoot 'src/Doorstop')); initialApiMapIncluded=$false; testPluginsIncluded=$false; files=@($manifest)} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stageRoot 'BepInEx/compatibility/package-manifest.json') -Encoding utf8

if (-not $StageOnly) {
    Write-Zip $stageRoot $zipPath @('BepInEx/plugins/','BepInEx/patchers/')
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName })
        foreach ($required in @('winhttp.dll','doorstop_config.ini','BepInEx/core/BepInEx.MetadataBootstrap.dll','BepInEx/core/BepInEx.Unity.IL2CPP.dll','BepInEx/compatibility/tools/prepare_api_map.py','BepInEx/compatibility/python/python.exe','BepInEx/core/scripts/normalize_metadata.py','dotnet/coreclr.dll','BepInEx/plugins/','BepInEx/compatibility/source.zip')) {
            if ($required -cnotin $names) { throw "The ZIP is missing required path: $required" }
        }
        foreach ($name in $names) {
            if ($name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)|^[A-Za-z]:|\\') { throw "Unsafe ZIP entry: $name" }
            if ($name -match '(^|/)CarXDoorstop(/|$)') { throw 'The ZIP contains an obsolete enclosing folder.' }
        }
    } finally { $archive.Dispose() }
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    ($hash + '  ' + [IO.Path]::GetFileName($zipPath)) | Set-Content -LiteralPath ($zipPath + '.sha256') -Encoding ascii
}
[pscustomobject]@{
    StagePath=$stageRoot
    SourcePath=$sourceStage
    ZipPath=$(if ($StageOnly) { $null } else { $zipPath })
    ZipBytes=$(if ($StageOnly) { $null } else { (Get-Item -LiteralPath $zipPath).Length })
    FileCount=@($manifest).Count + 1
    InitialApiMapIncluded=$false
    TestPluginsIncluded=$false
}
