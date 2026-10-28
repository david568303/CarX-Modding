# Shared by all release packagers. Keep the license paths identical to the repo.
function Get-PackageLicenseFiles([string]$ProjectRoot) {
    foreach ($name in @('LICENSE','THIRD-PARTY-NOTICES.md')) {
        if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $name) -PathType Leaf)) {
            throw "Required release licensing file is missing: $name"
        }
        @{Source=$name; Entry=$name}
    }
    $licenseRoot = Join-Path $ProjectRoot 'licenses'
    if (-not (Test-Path -LiteralPath $licenseRoot -PathType Container)) { throw 'The third-party licenses directory is missing.' }
    $count = 0
    foreach ($item in Get-ChildItem -LiteralPath $licenseRoot -Recurse -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Release licenses must be ordinary files, not links.' }
        if ($item.PSIsContainer) { continue }
        $relative = [IO.Path]::GetRelativePath($ProjectRoot,$item.FullName).Replace('\','/')
        @{Source=$relative; Entry=$relative}
        $count++
    }
    if ($count -eq 0) { throw 'The third-party licenses directory is empty.' }
}
