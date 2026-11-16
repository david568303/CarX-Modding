param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9]+(\.[0-9]+){2,3}$')][string]$Version,
    [Parameter(Mandatory)][string]$CapstoneDll,
    [Parameter(Mandatory)][string]$DobbyDll,
    [Parameter(Mandatory)][string]$Il2CppCommonDll,
    [string]$Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$doorstopRoot = Join-Path $projectRoot 'src/Doorstop'
. (Join-Path $PSScriptRoot 'package-licenses.ps1')
Add-Type -AssemblyName System.IO.Compression

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Revision([string]$Directory) {
    $revision = & git -C $Directory rev-parse HEAD
    if ($LASTEXITCODE -or $revision -notmatch '^[0-9a-f]{40}$') { throw "Cannot identify source in $Directory." }
    $changes = @(& git -C $Directory status --porcelain)
    if ($LASTEXITCODE -or $changes.Count) { throw "Commit source changes before packaging: $Directory" }
    $revision
}

function Add-PackageFile([string]$Source, [string]$RelativePath) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Missing package input: $Source" }
    $target = Join-Path $stageRoot $RelativePath
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $target -Force
}

function Assert-RuntimePath([string]$Name) {
    if ($Name -match '(^|/)\.\.?(/|$)|^/|[:\\]') { throw "Unsafe package path: $Name" }
    if ($Name -match '(?i)\.(exe|bat|cmd|msi|py|pyc|pyd|whl|zip|rar|7z|pdb|log)$' -or
        $Name -match '(?i)(^|/)(compatibility|python|__pycache__|cache|interop|unity-libs|downloads)(/|$)' -or
        $Name -match '(?i)(^|/)(GameAssembly\.dll|UnityPlayer\.dll|global-metadata\.dat|doorstop_api\.ini|CarX\.BepInEx\.Verification\.dll|python[0-9]*\.dll|python[0-9]*\._pth)$') {
        throw "Unexpected file in the installable runtime: $Name"
    }
}

$rootRevision = Get-Revision $projectRoot
$nativeRevision = Get-Revision $doorstopRoot
$pinnedNative = & git -C $projectRoot rev-parse 'HEAD:src/Doorstop'
if ($LASTEXITCODE -or $pinnedNative -cne $nativeRevision) { throw 'Commit the matching Doorstop submodule revision first.' }

if (-not $Destination) {
    $Destination = Join-Path $projectRoot "release/CarX-Drift-Racing-Online-2-BepInEx-Runtime-$Version.zip"
}
$zipPath = [IO.Path]::GetFullPath($Destination)
if ([IO.Path]::GetExtension($zipPath) -ine '.zip' -or (Test-Path -LiteralPath $zipPath)) {
    throw 'Destination must be a new ZIP file.'
}
New-Item -ItemType Directory -Path (Split-Path $zipPath -Parent) -Force | Out-Null
$stageRoot = Join-Path $projectRoot ('.work/package/stage-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

$officialPath = & (Join-Path $PSScriptRoot 'prepare-bepinex.ps1') -ArchiveOnly
$official = [IO.Compression.ZipFile]::OpenRead($officialPath)
try {
    foreach ($entry in $official.Entries) {
        $name = $entry.FullName
        if ($name -notmatch '^(BepInEx/core|dotnet)/' -or $name.EndsWith('/') -or $name.EndsWith('.pdb')) { continue }
        Assert-RuntimePath $name
        $target = Join-Path $stageRoot $name
        New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target)
    }
} finally { $official.Dispose() }
Add-PackageFile $Il2CppCommonDll 'BepInEx/core/Il2CppInterop.Common.dll'
Add-PackageFile $DobbyDll 'BepInEx/core/dobby.dll'
Add-PackageFile $CapstoneDll 'BepInEx/core/CarX.Capstone.dll'
Add-PackageFile (Join-Path $projectRoot '.work/build/doorstop-x64/winhttp.dll') 'winhttp.dll'
Add-PackageFile (Join-Path $projectRoot '.work/build/doorstop-x64/.doorstop_version') '.doorstop_version'
Add-PackageFile (Join-Path $projectRoot '.work/build/MetadataBootstrap/Release/net6.0/BepInEx.MetadataBootstrap.dll') 'BepInEx/core/BepInEx.MetadataBootstrap.dll'

@"
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
"@ | Set-Content -LiteralPath (Join-Path $stageRoot 'doorstop_config.ini') -Encoding ascii

$legacyNotices = @('Capstone-Python-BSD.txt', 'Python-LICENSE.txt', 'pefile-MIT.txt')
$licenses = Get-Content -LiteralPath (Join-Path $projectRoot 'licenses/manifest.json') -Raw | ConvertFrom-Json
$licenses.notices = @($licenses.notices | Where-Object file -NotIn $legacyNotices)
foreach ($notice in $licenses.notices) {
    $file = Join-Path $projectRoot ('licenses/' + $notice.file)
    if ((Get-Sha256 $file) -ne $notice.sha256) { throw "License checksum mismatch: $($notice.file)" }
}

$sourceCompliance = 'licenses/SOURCE-COMPLIANCE.txt'
$licenseText = @(
    'CarX Drift Racing Online 2 runtime licenses and notices'
    'Section labels identify the original notice paths. All notices are included in this file.'
    foreach ($item in Get-PackageLicenseFiles $projectRoot) {
        if ([IO.Path]::GetFileName($item.Entry) -in $legacyNotices -or
            $item.Entry -in @('licenses/manifest.json', $sourceCompliance)) { continue }
        ''
        "===== $($item.Entry) ====="
        $text = Get-Content -LiteralPath (Join-Path $projectRoot $item.Source) -Raw
        if ($item.Source -eq 'THIRD-PARTY-NOTICES.md') {
            $text = $text.Replace('each runtime''s SOURCE-DOWNLOADS.txt', 'the exact corresponding source section below')
        }
        $text
    }
    ''
    '===== licenses/UnityDoorstop-fork-LGPL.txt ====='
    Get-Content -LiteralPath (Join-Path $doorstopRoot 'LICENSE') -Raw
    ''
    '===== licenses/manifest.json ====='
    $licenses | ConvertTo-Json -Depth 10
    ''
    "===== $sourceCompliance ====="
    $complianceText = Get-Content -LiteralPath (Join-Path $projectRoot $sourceCompliance) -Raw
    $complianceText.Replace('SOURCE-DOWNLOADS.txt at the root of the runtime ZIP', 'The exact corresponding source section below').Replace('SOURCE-DOWNLOADS.txt', 'the exact corresponding source section below')
)

$sources = @(
    @{component='CarX compatibility and build scripts'; repository='david568303/CarX-Modding'; commit=$rootRevision},
    @{component='Modified UnityDoorstop'; repository='david568303/UnityDoorstop'; commit=$nativeRevision},
    @{component='BepInEx'; repository='BepInEx/BepInEx'; commit='b782da4ac54e1072d2857f4a2f77c80c3ef08005'},
    @{component='Il2CppInterop'; repository='BepInEx/Il2CppInterop'; commit='dbda1cb353b0f4253345dc45136d170b9e50a5a0'},
    @{component='Capstone'; repository='capstone-engine/capstone'; commit='022575848782a4801fd150fdbc927effcbca0864'},
    @{component='Dobby'; repository='BepInEx/Dobby'; commit='888d971214900374edbca6206fad6ded8a2c1311'}
)
$sourceText = @('', 'EXACT CORRESPONDING SOURCE FOR THE WINDOWS X64 RUNTIME', '')
foreach ($source in $sources) {
    $source.url = "https://codeload.github.com/$($source.repository)/zip/$($source.commit)"
    $sourceText += @($source.component, $source.url, '')
}
$sourceText += @(
    'The CarX source and UnityDoorstop submodule are separate downloads.',
    'The CarX repository contains the Capstone and Dobby patches, build scripts and notices.',
    "Build instructions: https://github.com/david568303/CarX-Modding/blob/$rootRevision/docs/SOURCE-BUILDS.md"
)
($licenseText + $sourceText) | Set-Content -LiteralPath (Join-Path $stageRoot 'LICENSES') -Encoding utf8

$manifestName = 'BepInEx/core/package-manifest.json'
$files = @(foreach ($item in Get-ChildItem -LiteralPath $stageRoot -File -Recurse -Force | Sort-Object FullName) {
    $name = [IO.Path]::GetRelativePath($stageRoot, $item.FullName).Replace('\','/')
    Assert-RuntimePath $name
    [ordered]@{path=$name; length=$item.Length; sha256=(Get-Sha256 $item.FullName)}
})
$required = @(
    'LICENSES', 'doorstop_config.ini', 'winhttp.dll',
    'BepInEx/core/CarX.Capstone.dll', 'BepInEx/core/BepInEx.MetadataBootstrap.dll',
    'BepInEx/core/BepInEx.Unity.IL2CPP.dll', 'BepInEx/core/Iced.dll', 'dotnet/coreclr.dll'
)
foreach ($name in $required) {
    if ($name -cnotin $files.path) { throw "Missing required runtime file: $name" }
}
[ordered]@{
    format=1; version=$Version; profile='python-free-runtime'
    sourceRevision=@{commit=$rootRevision; dirty=$false}
    doorstopRevision=@{commit=$nativeRevision; dirty=$false}
    correspondingSources=$sources
    initialApiMapIncluded=$false; testPluginsIncluded=$false; files=$files
} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $stageRoot $manifestName) -Encoding utf8

$temporaryZip = $zipPath + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
$archive = [IO.Compression.ZipFile]::Open($temporaryZip, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($directory in @('BepInEx/plugins/', 'BepInEx/patchers/')) { $null = $archive.CreateEntry($directory) }
    foreach ($name in @($files.path) + $manifestName) {
        $null = [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, (Join-Path $stageRoot $name), $name, [IO.Compression.CompressionLevel]::Optimal)
    }
} finally { $archive.Dispose() }

$archive = [IO.Compression.ZipFile]::OpenRead($temporaryZip)
try {
    if ($archive.Entries.Count -ne $files.Count + 3) { throw 'Unexpected number of ZIP entries.' }
    foreach ($record in $files) {
        $entry = $archive.GetEntry($record.path)
        if (-not $entry -or $entry.Length -ne $record.length) { throw "Invalid ZIP member: $($record.path)" }
        $stream = $entry.Open()
        try { $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream)).ToLowerInvariant() }
        finally { $stream.Dispose() }
        if ($hash -ne $record.sha256) { throw "ZIP checksum mismatch: $($record.path)" }
    }
} finally { $archive.Dispose() }

[IO.File]::Move($temporaryZip, $zipPath)
$hash = Get-Sha256 $zipPath
"$hash  $([IO.Path]::GetFileName($zipPath))" | Set-Content -LiteralPath ($zipPath + '.sha256') -Encoding ascii
[pscustomobject]@{ZipPath=$zipPath; StagePath=$stageRoot; SHA256=$hash; FileCount=($files.Count + 1)}
