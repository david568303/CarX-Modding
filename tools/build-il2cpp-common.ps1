[CmdletBinding(DefaultParameterSetName='SourceArchive')]
param(
    [Parameter(Mandatory, ParameterSetName='SourceArchive')][string]$SourceZip,
    [Parameter(Mandatory, ParameterSetName='RuntimeArchive')][string]$RuntimeZip,
    [string]$BuildRoot
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $BuildRoot) { $BuildRoot = Join-Path $projectRoot '.work/build/Il2CppInterop.Common-source' }
$BuildRoot = [IO.Path]::GetFullPath($BuildRoot)
if (Test-Path -LiteralPath $BuildRoot) { throw 'BuildRoot must be a new directory; existing inputs and outputs are never overwritten.' }

# Exact upstream 1.5.3 source; no source rewriting, feature removal or binary editing.
$sourceCommit = 'dbda1cb353b0f4253345dc45136d170b9e50a5a0'
$sourceSha256 = '96d223a475c885ef08118a3adaee0c2ed5d65edd83fbea9987e5a305f1123ac5'
$auditedRuntimeSha256 = 'e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e'
$originalCommonSha256 = '070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f'
$archiveRoot = 'Il2CppInterop-' + $sourceCommit
$sourceRoot = Join-Path $BuildRoot $archiveRoot
$originalCommon = $null
$inputRuntimeSha256 = $null
Add-Type -AssemblyName System.IO.Compression

function Get-BytesHash([byte[]]$Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Read-ZipMember([IO.Compression.ZipArchive]$Archive, [string]$Name) {
    $entry = $Archive.GetEntry($Name)
    if (-not $entry) { throw "Required archive member is missing: $Name" }
    $inputStream = $entry.Open()
    $memory = [IO.MemoryStream]::new()
    try { $inputStream.CopyTo($memory); return ,$memory.ToArray() }
    finally { $inputStream.Dispose(); $memory.Dispose() }
}

# Validate all trusted input bytes before creating a build directory or executing tools.
if ($PSCmdlet.ParameterSetName -eq 'RuntimeArchive') {
    $runtimePath = (Resolve-Path -LiteralPath $RuntimeZip).Path
    $inputRuntimeSha256 = (Get-FileHash -LiteralPath $runtimePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($inputRuntimeSha256 -ne $auditedRuntimeSha256) { throw 'RuntimeZip does not match the pinned audited build.' }
    $runtimeArchive = [IO.Compression.ZipFile]::OpenRead($runtimePath)
    try {
        $sourceBytes = Read-ZipMember $runtimeArchive 'BepInEx/compatibility/sources/Il2CppInterop-source-dbda1cb.zip'
        $originalCommon = Read-ZipMember $runtimeArchive 'BepInEx/core/Il2CppInterop.Common.dll'
        if ((Get-BytesHash $originalCommon) -ne $originalCommonSha256) { throw 'Original Common DLL does not match the audited upstream file.' }
    } finally { $runtimeArchive.Dispose() }
} else {
    $sourceBytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $SourceZip).Path)
}
if ((Get-BytesHash $sourceBytes) -ne $sourceSha256) { throw 'SourceZip does not match the pinned official corresponding source.' }

$memory = [IO.MemoryStream]::new($sourceBytes, $false)
$sourceArchive = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Read)
$sourceRecords = [Collections.Generic.List[object]]::new()
try {
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $sourceArchive.Entries) {
        $destination = [IO.Path]::GetFullPath((Join-Path $BuildRoot $entry.FullName))
        if (-not $destination.StartsWith($BuildRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
            -not $entry.FullName.StartsWith($archiveRoot + '/', [StringComparison]::Ordinal) -or
            $entry.FullName.Contains('\') -or (($entry.ExternalAttributes -shr 16) -band 0xf000) -eq 0xa000) {
            throw "Unsafe source archive member: $($entry.FullName)"
        }
        if ($entry.FullName.EndsWith('/')) { continue }
        if (-not $seen.Add($entry.FullName)) { throw 'Duplicate source archive member.' }
    }
    New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
    $inputRoot = Join-Path $BuildRoot 'inputs'
    New-Item -ItemType Directory -Path $inputRoot -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $inputRoot 'Il2CppInterop-source-dbda1cb.zip'), $sourceBytes)
    if ($originalCommon) { [IO.File]::WriteAllBytes((Join-Path $inputRoot 'Il2CppInterop.Common.original.dll'), $originalCommon) }
    foreach ($entry in $sourceArchive.Entries) {
        $destination = [IO.Path]::GetFullPath((Join-Path $BuildRoot $entry.FullName))
        if ($entry.FullName.EndsWith('/')) { New-Item -ItemType Directory -Path $destination -Force | Out-Null; continue }
        $bytes = Read-ZipMember $sourceArchive $entry.FullName
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        [IO.File]::WriteAllBytes($destination, $bytes)
        $sourceRecords.Add([ordered]@{path=$entry.FullName.Substring($archiveRoot.Length + 1); sha256=(Get-BytesHash $bytes)})
    }
} finally { $sourceArchive.Dispose(); $memory.Dispose() }

# Supported SDK selection only: compile the unchanged netstandard2.0 project
# with an already installed later SDK. No compiler or system runtime is installed.
$globalPath = Join-Path $sourceRoot 'global.json'
$globalOriginal = Get-Content -LiteralPath $globalPath -Raw
$globalOriginal | Set-Content -LiteralPath (Join-Path $inputRoot 'global.original.json') -Encoding utf8
$globalConfig = $globalOriginal | ConvertFrom-Json
if ($globalConfig.sdk.version -ne '8.0.0' -or $globalConfig.sdk.rollForward -ne 'latestFeature') { throw 'Unexpected upstream SDK selection configuration.' }
$globalConfig.sdk.rollForward = 'latestMajor'
$globalConfig | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $globalPath -Encoding utf8

$project = Join-Path $sourceRoot 'Il2CppInterop.Common/Il2CppInterop.Common.csproj'
$arguments = @('build', $project, '-c', 'Release', '--nologo',
    '-p:ContinuousIntegrationBuild=true', '-p:EnableSourceControlManagerQueries=false',
    ('-p:SourceRevisionId=' + $sourceCommit), ('-p:RepositoryCommit=' + $sourceCommit),
    '-p:RepositoryUrl=https://github.com/BepInEx/Il2CppInterop',
    ('-p:PathMap=' + $sourceRoot + '=/_/Il2CppInterop'))
Push-Location $sourceRoot
try {
    $sdk = & dotnet --version
    if ($LASTEXITCODE -ne 0) { throw 'An existing dotnet SDK could not be selected. No compiler will be installed.' }
    & dotnet @arguments 2>&1 | Tee-Object -FilePath (Join-Path $BuildRoot 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'The unchanged upstream Common project did not build successfully.' }
} finally { Pop-Location }

# Guard against accidental source changes during preparation/build. global.json
# is the sole documented toolchain-selection change; C# and project bytes stay exact.
foreach ($record in $sourceRecords) {
    if ($record.path -eq 'global.json') { continue }
    $actual = (Get-FileHash -LiteralPath (Join-Path $sourceRoot $record.path) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $record.sha256) { throw "An upstream source file changed: $($record.path)" }
}
$sourceRecords | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $inputRoot 'source-files.json') -Encoding utf8
$builtDll = Join-Path $sourceRoot 'bin/Il2CppInterop.Common/netstandard2.0/Il2CppInterop.Common.dll'
if (-not (Test-Path -LiteralPath $builtDll -PathType Leaf)) { throw 'Expected upstream Common output was not found.' }
$candidateRoot = Join-Path $BuildRoot 'candidate'
New-Item -ItemType Directory -Path $candidateRoot -Force | Out-Null
$candidatePath = Join-Path $candidateRoot 'Il2CppInterop.Common.dll'
Copy-Item -LiteralPath $builtDll -Destination $candidatePath
$record = [ordered]@{
    sourceCommit=$sourceCommit; sourceArchiveSha256=$sourceSha256
    sourceArchiveUrl=('https://codeload.github.com/BepInEx/Il2CppInterop/zip/' + $sourceCommit)
    inputRuntimeSha256=$inputRuntimeSha256; originalCommonSha256=$originalCommonSha256
    sdk=[string]$sdk; configuration='Release'; targetFramework='netstandard2.0'; debugType='embedded'
    sourceFilesVerified=$sourceRecords.Count
    sourceChanges=@('global.json: sdk.rollForward latestFeature -> latestMajor; SDK selection only')
    command=@('dotnet') + $arguments; candidate=$candidatePath
    bytes=(Get-Item -LiteralPath $candidatePath).Length
    sha256=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
    note='The DLL is a compatible source-build candidate; a scanner result must be verified separately.'
}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $BuildRoot 'build-record.json') -Encoding utf8
$record | ConvertTo-Json -Depth 6
