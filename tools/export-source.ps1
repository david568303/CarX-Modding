param([Parameter(Mandatory)][string]$Version)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw 'Use a plain release version without paths.' }
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$submoduleRoot = Join-Path $projectRoot 'src/Doorstop'
$releaseRoot = Join-Path $projectRoot 'release'
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
$revision = & git -C $projectRoot rev-parse HEAD
if ($LASTEXITCODE) { throw 'Commit the source before exporting.' }
$doorstopRevision = & git -C $submoduleRoot rev-parse HEAD
if ($LASTEXITCODE) { throw 'Initialize the Doorstop submodule first.' }
$pinnedRevision = & git -C $projectRoot rev-parse 'HEAD:src/Doorstop'
if ($LASTEXITCODE -or $pinnedRevision -cne $doorstopRevision) { throw 'Doorstop must match the committed submodule revision.' }
foreach ($directory in @($projectRoot, $submoduleRoot)) {
    $changes = @(& git -C $directory status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -or $changes.Count -ne 0) { throw "Commit all source changes before exporting: $directory" }
}
$output = Join-Path $releaseRoot "CarX-Modding-Source-$Version.zip"
Add-Type -AssemblyName System.IO.Compression
$stream = [IO.File]::Create($output)
try {
    $zip = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($source in @(@{Root=$projectRoot; Prefix=''}, @{Root=$submoduleRoot; Prefix='src/Doorstop/'})) {
            $paths = @(& git -C $source.Root -c core.quotepath=false ls-files)
            if ($LASTEXITCODE) { throw 'Cannot enumerate tracked source.' }
            foreach ($relative in $paths) {
                if ($source.Prefix -eq '' -and $relative -eq 'src/Doorstop') { continue }
                $file = Join-Path $source.Root $relative
                if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing source: $relative" }
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file, ($source.Prefix + $relative), [IO.Compression.CompressionLevel]::Optimal) | Out-Null
            }
        }
        $entry = $zip.CreateEntry('SOURCE-REVISION.json')
        $writer = [IO.StreamWriter]::new($entry.Open(), [Text.UTF8Encoding]::new($false))
        try {
            $writer.Write((@{repository='https://github.com/david568303/CarX-Modding'; revision=$revision; doorstopRevision=$doorstopRevision; version=$Version} | ConvertTo-Json))
        } finally { $writer.Dispose() }
    } finally { $zip.Dispose() }
} finally { $stream.Dispose() }
$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($output))" | Set-Content -LiteralPath ($output + '.sha256') -Encoding ascii
Write-Output $output
