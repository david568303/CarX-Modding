param(
    [Parameter(Mandatory)][string]$ZipPath,
    [string]$GameDirectory = $env:CARX_GAME_DIRECTORY,
    [string]$RunBase = [IO.Path]::GetTempPath(),
    [string]$ReuseGameCopyFrom,
    [ValidateRange(1,300)][int]$TimeoutSeconds = 300,
    [switch]$StripDebugDirectories
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$zip = (Resolve-Path -LiteralPath $ZipPath).Path
if (-not $GameDirectory) { throw 'Pass -GameDirectory or set CARX_GAME_DIRECTORY to the installed game folder.' }
$gameRoot = (Resolve-Path -LiteralPath $GameDirectory).Path.TrimEnd('\')
if ([IO.Path]::GetExtension($zip) -ine '.zip') { throw 'ZipPath must identify the release ZIP.' }

function Assert-ChildPath([string]$Base, [string]$Candidate) {
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd('\')
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    if (-not $candidateFull.StartsWith($baseFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escaped its intended directory: $candidateFull"
    }
    return $candidateFull
}
function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-OrdinaryDirectory([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Expected an ordinary directory: $Path"
    }
}
function Assert-OutsideGame([string]$Directory) {
    if ($Directory.Equals($gameRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $Directory.StartsWith($gameRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Test staging and evidence must be outside the original game installation.'
    }
    for ($parent = [IO.DirectoryInfo]::new($Directory); $null -ne $parent; $parent = $parent.Parent) {
        Assert-OrdinaryDirectory $parent.FullName
    }
}
function Copy-TestTree([string]$Source, [string]$Destination) {
    Assert-OrdinaryDirectory $Source
    if (Test-Path -LiteralPath $Destination) { throw "The staging destination already exists: $Destination" }
    $null = New-Item -ItemType Directory -Path $Destination
    foreach ($item in Get-ChildItem -LiteralPath $Source -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Cannot stage a linked game dependency: $($item.FullName)"
        }
        $target = Assert-ChildPath $Destination (Join-Path $Destination $item.Name)
        if ($item.PSIsContainer) {
            Copy-TestTree $item.FullName $target
        } elseif (-not ($StripDebugDirectories -and $item.Extension -ieq '.pdb')) {
            [IO.File]::Copy($item.FullName, $target, $false)
        }
    }
}
function Assert-NoCarXProcess {
    if (Get-Process -Name 'CarX Drift Racing Online 2' -ErrorAction SilentlyContinue) {
        throw 'A CarX process is already running. The isolated game copy was not started.'
    }
}
function Move-TestTrees([string]$From, [string]$To, [string[]]$Names) {
    foreach ($name in $Names) {
        $source = Assert-ChildPath $From (Join-Path $From $name)
        $destination = Assert-ChildPath $To (Join-Path $To $name)
        Assert-OrdinaryDirectory $source
        if (Test-Path -LiteralPath $destination) { throw "The staging destination already exists: $destination" }
        if (Get-ChildItem -LiteralPath $source -Force -Recurse -Attributes ReparsePoint) {
            throw "The prior staged game tree contains a link: $source"
        }
    }
    $moved = @()
    try {
        foreach ($name in $Names) {
            [IO.Directory]::Move((Join-Path $From $name), (Join-Path $To $name))
            $moved += $name
        }
    } catch {
        foreach ($name in $moved) { [IO.Directory]::Move((Join-Path $To $name), (Join-Path $From $name)) }
        throw
    }
}
function Get-InputSnapshot {
    $snapshot = [ordered]@{}
    foreach ($relative in $inputFiles) {
        $path = Assert-ChildPath $gameRoot (Join-Path $gameRoot $relative)
        $item = Get-Item -LiteralPath $path -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Expected an ordinary game input file: $relative"
        }
        $snapshot[$relative] = [ordered]@{sha256=(Get-Sha256 $path); length=$item.Length}
    }
    return $snapshot
}
function Convert-Domain([object]$Value) {
    $text = [string]$Value
    if ($text -notmatch '^0x[0-9A-Fa-f]+$') { throw "Invalid domain proof value: $text" }
    return [UInt64]::Parse($text.Substring(2), [Globalization.NumberStyles]::HexNumber)
}
function Clear-TestDebugDirectory([string]$Path) {
    # Remove the CodeView records and their locator only in the isolated copied
    # PE. Exports, imports, native code, unwind data and originals stay intact.
    $stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
        $reader = [IO.BinaryReader]::new($stream,[Text.Encoding]::UTF8,$true)
        $stream.Position=0x3c; $peOffset=$reader.ReadUInt32()
        $stream.Position=$peOffset
        if ($reader.ReadUInt32() -ne 0x4550) { throw 'A copied PE has an invalid signature.' }
        $stream.Position=$peOffset+6; $sectionCount=$reader.ReadUInt16()
        $stream.Position=$peOffset+20; $optionalSize=$reader.ReadUInt16()
        $stream.Position=$peOffset+24; $magic=$reader.ReadUInt16()
        if ($magic -ne 0x20b) { throw 'The debug-directory test requires a PE32+ input.' }
        $debugDirectory=$peOffset+24+112+6*8
        $sectionTable=$peOffset+24+$optionalSize
        if ($optionalSize -lt 168 -or $sectionCount -gt 96 -or $sectionTable+$sectionCount*40 -gt $stream.Length) { throw 'The copied PE section table is invalid.' }
        $stream.Position=$debugDirectory
        $debugRva=$reader.ReadUInt32(); $debugSize=$reader.ReadUInt32()
        $debugRaw=$null
        if ($debugRva -and $debugSize) {
            if ($debugSize % 28 -ne 0 -or $debugSize -gt 65536) { throw 'The copied PE debug directory is malformed.' }
            for($index=0;$index -lt $sectionCount;$index++) {
                $stream.Position=$sectionTable+$index*40+8
                $virtualSize=$reader.ReadUInt32(); $virtualRva=$reader.ReadUInt32()
                $rawSize=$reader.ReadUInt32(); $rawOffset=$reader.ReadUInt32()
                if($debugRva -ge $virtualRva -and $debugRva-$virtualRva -lt $rawSize) {
                    $debugRaw=[long]$rawOffset+$debugRva-$virtualRva
                    break
                }
            }
            if($null -eq $debugRaw -or $debugRaw+$debugSize -gt $stream.Length) { throw 'The copied PE debug directory cannot be mapped.' }
        }
        $clearedRecords=0
        if($null -ne $debugRaw) {
            for($offset=0;$offset -lt $debugSize;$offset+=28) {
                $stream.Position=$debugRaw+$offset+12
                $type=$reader.ReadUInt32(); $size=$reader.ReadUInt32()
                $null=$reader.ReadUInt32(); $raw=$reader.ReadUInt32()
                if($type -eq 2 -and $size) {
                    if($size -gt 1048576 -or [long]$raw+$size -gt $stream.Length -or
                       ([long]$raw -lt $debugRaw+$debugSize -and [long]$raw+$size -gt $debugRaw)) { throw 'The copied CodeView data is invalid.' }
                    $stream.Position=$raw
                    $stream.Write([byte[]]::new($size),0,$size)
                    $clearedRecords++
                }
            }
            $stream.Position=$debugRaw
            $stream.Write([byte[]]::new($debugSize),0,$debugSize)
        }
        $stream.Position=$debugDirectory
        $stream.Write([byte[]]::new(8),0,8)
        $stream.Flush()
        $stream.Position=$debugDirectory
        if ($reader.ReadUInt64() -ne 0) { throw 'The copied PE debug directory was not cleared.' }
        $reader.Dispose()
        return [ordered]@{file=[IO.Path]::GetFileName($Path); codeViewRecordsCleared=$clearedRecords; directoryCleared=$true}
    } finally { $stream.Dispose() }
}

$rootBinaries = @('CarX Drift Racing Online 2.exe','UnityPlayer.dll','GameAssembly.dll','baselib.dll','nvngx_dlss.dll','NVUnityPlugin.dll','UnityCrashHandler64.exe')
$inputFiles = @($rootBinaries) + @('CarX Drift Racing Online 2_Data\il2cpp_data\Metadata\global-metadata.dat')
$pluginSource = Join-Path $projectRoot '.work/build/VerificationPlugin/Release/net6.0/CarX.BepInEx.Verification.dll'
if (-not (Test-Path -LiteralPath $pluginSource -PathType Leaf)) { throw 'Build tests/VerificationPlugin before running the release test.' }
$zipHashBefore = Get-Sha256 $zip
$sidecar = $zip + '.sha256'
if (Test-Path -LiteralPath $sidecar -PathType Leaf) {
    $hashText = (Get-Content -LiteralPath $sidecar -Raw).Trim()
    if ($hashText -notmatch '^([0-9A-Fa-f]{64})(?:\s|$)' -or $Matches[1].ToLowerInvariant() -ne $zipHashBefore) {
        throw 'The release ZIP does not match its SHA-256 sidecar.'
    }
}
Assert-OrdinaryDirectory $gameRoot
$workRoot = Assert-ChildPath $projectRoot (Join-Path $projectRoot '.work')
$runBase = (Resolve-Path -LiteralPath $RunBase).Path
Assert-OutsideGame $workRoot
Assert-OutsideGame $runBase
$evidenceBase = Join-Path $workRoot 'verification'
if (-not (Test-Path -LiteralPath $evidenceBase)) { $null = New-Item -ItemType Directory -Path $evidenceBase }
Assert-OrdinaryDirectory $evidenceBase
$runId = [Guid]::NewGuid().ToString('N')
$runRoot = Assert-ChildPath $runBase (Join-Path $runBase ('CarX-' + $runId.Substring(0,12)))
$evidenceRoot = Assert-ChildPath $evidenceBase (Join-Path $evidenceBase ('release-test-' + $runId))
$originalBefore = Get-InputSnapshot
New-Item -ItemType Directory -Path $runRoot,$evidenceRoot | Out-Null

$process = $null
$exitCode = $null
$launchTime = $null
$failure = $null
$timedOut = $false
$manifestVerified = $false
$isolatedGameCopyVerified = $false
$reusedGameCopyFrom = $null
$originalUnchanged = $false
$zipUnchanged = $false
$zipHashAfter = $null
$originalAfter = $null
$proof = $null
$interopCount = 0
$strippedDebugInfo = @()
$playerLog = Join-Path $runRoot 'Player.release-test.log'
$bepLog = Join-Path $runRoot 'BepInEx/LogOutput.log'
$proofPath = Join-Path $runRoot 'BepInEx/verification-plugin.json'
$metadataLog = Join-Path $runRoot 'BepInEx/metadata-bootstrap.log'
$apiLog = Join-Path $runRoot 'BepInEx/cache/compatibility/api-refresh.log'
try {
    # Validate every archive path before extraction, including duplicate names.
    Add-Type -AssemblyName System.IO.Compression
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    $archiveFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $archiveNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    try {
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName
            if ($name.StartsWith('/') -or $name -match '(^|/)\.\.?(/|$)|[:\\]|//|[ .](/|$)' -or
                (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {
                throw "Unsafe ZIP entry: $name"
            }
            $null = Assert-ChildPath $runRoot (Join-Path $runRoot $name.Replace('/','\'))
            if (-not $archiveNames.Add($name)) { throw "Duplicate ZIP entry: $name" }
            if ($name -match '(?i)(^|/)(python|__pycache__)(/|$)' -or
                $name -match '(?i)\.(py|pyw|pyc|pyo|pyd|whl|_pth)$' -or
                $name -match '(?i)(^|/)python(?:[0-9]+|w)?\.(exe|dll|zip|cat)$') {
                throw "The release ZIP contains a Python artifact: $name"
            }
            if ($name.EndsWith('/')) { continue }
            if ($name -match '(?i)(^|/)(GameAssembly\.dll|UnityPlayer\.dll|CarX Drift Racing Online 2\.exe|global-metadata\.dat|doorstop_api\.ini|api-map\.json|verification-plugin\.json|Verification\.dll|CarX\.BepInEx\.Verification\.dll)$' -or
                $name -match '(?i)(^|/)(interop|unity-libs|cache|downloads)(/|$)' -or
                $name -match '(?i)\.(exe|bat|cmd|msi|zip|rar|7z|pdb|log)$' -or
                $name -match '(?i)(^|/)(pdbsymbols\.[^/]+|msdia[^/]*)$') {
                throw "The release ZIP contains an unexpected runtime artifact: $name"
            }
            $null = $archiveFiles.Add($name)
        }
    } finally { $archive.Dispose() }
    Expand-Archive -LiteralPath $zip -DestinationPath $runRoot
    $manifestRelative = 'BepInEx/compatibility/package-manifest.json'
    $manifestPath = Join-Path $runRoot $manifestRelative
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.format -ne 1 -or $manifest.initialApiMapIncluded -ne $false -or $manifest.testPluginsIncluded -ne $false -or
        $manifest.profile -cne 'python-free-runtime') {
        throw 'The package manifest does not describe a clean Python-free first-launch release.'
    }
    $manifestPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($file in @($manifest.files)) {
        $relative = [string]$file.path
        if (-not $archiveFiles.Contains($relative) -or -not $manifestPaths.Add($relative)) { throw "Manifest entry is absent or duplicated: $relative" }
        $path = Assert-ChildPath $runRoot (Join-Path $runRoot $relative.Replace('/','\'))
        $item = Get-Item -LiteralPath $path -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            $item.Length -ne $file.length -or (Get-Sha256 $path) -ne ([string]$file.sha256).ToLowerInvariant()) {
            throw "Package manifest verification failed: $relative"
        }
    }
    if ($archiveFiles.Count -ne $manifestPaths.Count + 1 -or -not $archiveFiles.Contains($manifestRelative)) {
        throw 'The ZIP contains files not accounted for by its package manifest.'
    }
    $manifestVerified = $true

    # Copy matching input binaries; the original installation stays read-only.
    foreach ($name in $rootBinaries) {
        $source = Assert-ChildPath $gameRoot (Join-Path $gameRoot $name)
        $destination = Assert-ChildPath $runRoot (Join-Path $runRoot $name)
        if (Test-Path -LiteralPath $destination) { throw "The ZIP unexpectedly included a game binary: $name" }
        Copy-Item -LiteralPath $source -Destination $destination
        if ((Get-Sha256 $destination) -ne $originalBefore[$name].sha256) { throw "The copied game input changed during staging: $name" }
    }
    if ($StripDebugDirectories) {
        foreach ($name in @('UnityPlayer.dll','GameAssembly.dll')) {
            $strippedDebugInfo += Clear-TestDebugDirectory (Assert-ChildPath $runRoot (Join-Path $runRoot $name))
        }
    }
    $metadataInput = $inputFiles[-1]
    $gameTrees = @('CarX Drift Racing Online 2_Data','D3D12')
    if ($ReuseGameCopyFrom) {
        # Transfer only the previously copied game assets to a fresh runtime.
        # The prior run's package, plugin proof and caches stay in its directory.
        Assert-NoCarXProcess
        $priorResultPath = (Resolve-Path -LiteralPath $ReuseGameCopyFrom).Path
        $priorEvidence = Split-Path $priorResultPath -Parent
        $priorName = Split-Path $priorEvidence -Leaf
        if ((Split-Path $priorEvidence -Parent) -ine $evidenceBase -or
            (Split-Path $priorResultPath -Leaf) -ine 'result.json' -or $priorName -notmatch '^release-test-([a-f0-9]{32})$') {
            throw 'ReuseGameCopyFrom must identify a prior result from this worktree.'
        }
        $priorRunRoot = Assert-ChildPath $runBase (Join-Path $runBase ('CarX-' + $Matches[1].Substring(0,12)))
        Assert-OrdinaryDirectory $priorEvidence
        Assert-OrdinaryDirectory $priorRunRoot
        $prior = Get-Content -LiteralPath $priorResultPath -Raw | ConvertFrom-Json -AsHashtable
        if ($prior.runRoot -ine $priorRunRoot -or $prior.isolatedGameCopyVerified -ne $true -or $prior.originalInputsUnchanged -ne $true -or
            ($StripDebugDirectories -and $prior.copiedDebugDirectoriesStripped -ne $true)) {
            throw 'Prior evidence does not establish an isolated game copy for this test.'
        }
        foreach ($name in $inputFiles) {
            if ($prior.originalInputsBefore[$name].sha256 -cne $originalBefore[$name].sha256) {
                throw "The installed game inputs have changed since the prior run: $name"
            }
        }
        if ((Get-Sha256 (Join-Path $priorRunRoot $metadataInput)) -ne $originalBefore[$metadataInput].sha256) {
            throw 'The prior staged metadata differs from the original input.'
        }
        Move-TestTrees $priorRunRoot $runRoot $gameTrees
        $reusedGameCopyFrom = $priorRunRoot
    } else {
        foreach ($name in $gameTrees) {
            $source = Assert-ChildPath $gameRoot (Join-Path $gameRoot $name)
            $destination = Assert-ChildPath $runRoot (Join-Path $runRoot $name)
            Copy-TestTree $source $destination
        }
    }
    if ((Get-Sha256 (Join-Path $runRoot $metadataInput)) -ne $originalBefore[$metadataInput].sha256) {
        throw 'The copied original metadata changed during staging.'
    }
    $isolatedGameCopyVerified = $true
    $pluginDirectory = Join-Path $runRoot 'BepInEx/plugins'
    New-Item -ItemType Directory -Path $pluginDirectory -Force | Out-Null
    Copy-Item -LiteralPath $pluginSource -Destination (Join-Path $pluginDirectory 'CarX.BepInEx.Verification.dll')
    foreach ($relative in @('doorstop_api.ini','BepInEx/cache','BepInEx/interop','BepInEx/unity-libs')) {
        if (Test-Path -LiteralPath (Join-Path $runRoot $relative)) { throw "The fresh first-launch test contains an unexpected cache: $relative" }
    }
    $executable = Join-Path $runRoot 'CarX Drift Racing Online 2.exe'
    Assert-NoCarXProcess
    $startInfo = [Diagnostics.ProcessStartInfo]::new($executable)
    $startInfo.WorkingDirectory = $runRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    foreach ($argument in @('-batchmode','-nographics','-logFile',$playerLog)) { $startInfo.ArgumentList.Add($argument) }
    foreach ($name in @($startInfo.Environment.Keys)) {
        if ($name -match '^(BEPINEX|DOORSTOP)_') { $null = $startInfo.Environment.Remove($name) }
    }
    $startInfo.Environment['BEPINEX_VERIFY_EXIT'] = '1'
    $launchTime = [DateTime]::UtcNow
    $process = [Diagnostics.Process]::Start($startInfo)
    Write-Host "Testing clean release in $runRoot"
    Write-Host "Game process $($process.Id); first launch must generate its own API, metadata and interop caches."
    $deadline = $launchTime.AddSeconds($TimeoutSeconds)
    $lastLine = $null
    while ($true) {
        $remaining = [int][Math]::Ceiling(($deadline - [DateTime]::UtcNow).TotalMilliseconds)
        if ($remaining -le 0) {
            $timedOut = $true
            if (-not $process.HasExited) { $process.Kill(); $null = $process.WaitForExit(10000) }
            throw "The owned release-test process exceeded $TimeoutSeconds seconds."
        }
        $finished = $process.WaitForExit([Math]::Min(10000,$remaining))
        if (Test-Path -LiteralPath $bepLog -PathType Leaf) {
            $line = @(Get-Content -LiteralPath $bepLog -Tail 1 -ErrorAction SilentlyContinue)
            if ($line.Count -and $line[0] -ne $lastLine) {
                $lastLine = $line[0]
                Write-Host $lastLine
            }
        }
        if ($finished) { break }
    }
    # Keep the original Process object so Windows exit-code state is retained.
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0) { throw "The release-test game process exited with code $exitCode." }
    $proofFile = Get-Item -LiteralPath $proofPath
    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    if ($proofFile.LastWriteTimeUtc -lt $launchTime -or $proof.processId -ne $process.Id -or $proof.BasePluginLoaded -ne $true -or
        -not [string]::Equals([IO.Path]::GetFullPath([string]$proof.processPath),$executable,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'The BepInEx verification proof is stale or belongs to a different process.'
    }
    $nativeDomain = Convert-Domain $proof.domainGetCanonicalNativeLibrary
    $pinvokeDomain = Convert-Domain $proof.domainGetCanonicalPInvoke
    $interopDomain = Convert-Domain $proof.domainGetIl2CppInteropRuntime
    if ($nativeDomain -eq 0 -or $nativeDomain -ne $pinvokeDomain -or $nativeDomain -ne $interopDomain -or
        $proof.nativeLibraryAndPInvokeAgree -ne $true -or $proof.nativeLibraryAndIl2CppInteropAgree -ne $true) {
        throw 'NativeLibrary, P/Invoke and Il2CppInterop did not agree on a nonzero domain.'
    }
    $logText = Get-Content -LiteralPath $bepLog -Raw
    if ($logText -notmatch 'Chainloader startup complete' -or $logText -notmatch 'CARX_BEPINEX_VERIFICATION_PLUGIN_LOADED') {
        throw 'The log does not prove both verification-plugin loading and completed BepInEx chainloader startup.'
    }
    foreach ($relative in @('doorstop_api.ini','BepInEx/cache/metadata/global-metadata.dat','BepInEx/cache/metadata/global-metadata.dat.fingerprint.json','BepInEx/cache/compatibility/api-refresh.log')) {
        $generated = Get-Item -LiteralPath (Join-Path $runRoot $relative)
        if ($generated.LastWriteTimeUtc -lt $launchTime) { throw "Generated first-launch output is stale: $relative" }
    }
    $interopCount = @(Get-ChildItem -LiteralPath (Join-Path $runRoot 'BepInEx/interop') -Filter '*.dll' -File).Count
    if ($interopCount -eq 0) { throw 'BepInEx did not generate any interop assemblies.' }
} catch {
    $failure = $_.Exception.Message
} finally {
    if ($process -and -not $process.HasExited) {
        # Never stop a pre-existing or independently launched process.
        $process.Kill()
        $null = $process.WaitForExit(10000)
    }
    if ($process -and $process.HasExited -and $null -eq $exitCode) { $exitCode = $process.ExitCode }
    try {
        $originalAfter = Get-InputSnapshot
        $originalUnchanged = ($originalBefore | ConvertTo-Json -Depth 5 -Compress) -ceq ($originalAfter | ConvertTo-Json -Depth 5 -Compress)
        $zipHashAfter = Get-Sha256 $zip
        $zipUnchanged = $zipHashBefore -ceq $zipHashAfter
        if (-not $originalUnchanged) { $failure = (@($failure,'Original game input SHA-256 values changed during the test.') | Where-Object { $_ }) -join ' ' }
        if (-not $zipUnchanged) { $failure = (@($failure,'The release ZIP changed during the test.') | Where-Object { $_ }) -join ' ' }
    } catch {
        $failure = (@($failure,$_.Exception.Message) | Where-Object { $_ }) -join ' '
    }
    foreach ($pair in @(
        @{Source=$proofPath; Name='plugin-proof.json'},
        @{Source=$bepLog; Name='BepInEx.log'},
        @{Source=$metadataLog; Name='metadata-bootstrap.log'},
        @{Source=$apiLog; Name='api-refresh.log'},
        @{Source=$playerLog; Name='Player.log'}
    )) {
        $target = Assert-ChildPath $evidenceRoot (Join-Path $evidenceRoot $pair.Name)
        if (Test-Path -LiteralPath $pair.Source -PathType Leaf) { Copy-Item -LiteralPath $pair.Source -Destination $target -Force }
        elseif ($pair.Name.EndsWith('.json')) { 'null' | Set-Content -LiteralPath $target -Encoding utf8 }
        else { 'This file was not produced by the latest release-test run.' | Set-Content -LiteralPath $target -Encoding utf8 }
    }
    $result = [ordered]@{
        success=($null -eq $failure)
        startedUtc=$(if ($launchTime) {$launchTime.ToString('o')} else {$null})
        finishedUtc=[DateTime]::UtcNow.ToString('o')
        zipPath=$zip
        zipSha256Before=$zipHashBefore
        zipSha256After=$zipHashAfter
        zipUnchanged=$zipUnchanged
        packageManifestVerified=$manifestVerified
        pythonFreePackageVerified=$manifestVerified
        isolatedGameCopyVerified=$isolatedGameCopyVerified
        reusedGameCopyFrom=$reusedGameCopyFrom
        runRoot=$runRoot
        processId=$(if ($process) {$process.Id} else {$null})
        exitCode=$exitCode
        timeoutSeconds=$TimeoutSeconds
        timedOut=$timedOut
        originalInputsUnchanged=$originalUnchanged
        originalInputsBefore=$originalBefore
        originalInputsAfter=$originalAfter
        generatedInteropAssemblyCount=$interopCount
        verificationPluginSha256=(Get-Sha256 $pluginSource)
        copiedDebugDirectoriesStripped=($strippedDebugInfo.Count -eq 2)
        copiedDebugRecords=@($strippedDebugInfo)
        evidenceDirectory=$evidenceRoot
        error=$failure
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot 'result.json') -Encoding utf8
    if ($process) { $process.Dispose() }
}
if ($failure) { throw "Release verification failed: $failure Evidence: $evidenceRoot" }
Write-Host "PASS: clean release completed BepInEx startup and loaded the verification plugin; original game inputs and release ZIP are unchanged."
[pscustomobject]@{ResultPath=(Join-Path $evidenceRoot 'result.json'); RunRoot=$runRoot; ProcessId=$result.processId; ExitCode=$exitCode}
