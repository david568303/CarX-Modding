# Publishing CarX Drift Racing Online 2 compatibility releases

These repositories publish the UnityDoorstop/BepInEx loader compatibility work
for **CarX Drift Racing Online 2** on Windows x64. Both belong to `david568303`:

1. `UnityDoorstop` retains the original upstream history and LGPL license. Its
   `carx-compatibility` branch contains the surviving native changes in separate commits.
2. `CarX-Modding` holds the compatibility integration sources, tests and releases.
   `src/Doorstop` pins the fork commit as a submodule; there is no releases-only repository.

## Work on source

Clone with `--recurse-submodules`. Commit meaningful changes separately. When changing
Doorstop, commit and push the fork first, then stage the updated `src/Doorstop` gitlink
in this repository and commit it. Keep the fork's LGPL notices and dated modification
notices. Keep private game binaries, generated interop, metadata, API maps, caches,
test evidence and dependency archives under ignored `.work/`.

The original upstream comparison and exact native commits are recorded in
[doorstop-diff.md](publication/doorstop-diff.md) and its complete patch. Abandoned
implementations are excluded from the publication.

## Build a release

Run the tests in [TESTING.md](TESTING.md), commit the final source and push it.
Set a new version, then run from the repository root:

```powershell
$version = '2026.10.28.1'
.\tools\build-release.ps1 -Version $version
```

This builds the loader using the installed tools, adds licenses to
both ZIPs, includes exact corresponding LGPL source with the loader, exports the
complete source with the Doorstop submodule expanded, and validates all assets.
The source exporter requires clean committed root/submodule trees and an exact pin.
Do not commit the generated `release/` directory.

The release output is:

- `BepInEx-Doorstop-NoPDB.zip`: complete loader and corresponding source.
- `CarX-Modding-Source-<version>.zip`: complete maintained source including Doorstop.
- Individual `.sha256` files, `SHA256SUMS.txt`, and `release-verification.json`.

Both ZIPs contain `LICENSE`, `THIRD-PARTY-NOTICES.md` and `licenses/`.
The loader's
`BepInEx/compatibility/source.zip` contains modified source/build instructions;
`BepInEx/compatibility/sources/` contains exact BepInEx and Il2CppInterop source.

## Upload to GitHub Releases

Write release notes describing the resulting behavior and actual validation.
Mention any remaining in-game test limitations. Save them to the ignored path
`release/RELEASE-NOTES.md`, then:

```powershell
git tag -a "v$version" -m "CarX compatibility $version"
git push origin "v$version"
$assets = @(
  'release/BepInEx-Doorstop-NoPDB.zip',
  "release/CarX-Modding-Source-$version.zip",
  'release/BepInEx-Doorstop-NoPDB.zip.sha256',
  "release/CarX-Modding-Source-$version.zip.sha256",
  'release/SHA256SUMS.txt',
  'release/release-verification.json',
  'LICENSE',
  'THIRD-PARTY-NOTICES.md'
)
gh release create "v$version" @assets --repo david568303/CarX-Modding --verify-tag --title "CarX compatibility $version" --notes-file release/RELEASE-NOTES.md
```

GitHub's automatic source download does not expand submodules. The explicit complete
source ZIP is therefore a required release asset. Required LGPL source is also inside
the installable loader ZIP, so that it remains available when that ZIP is redistributed.

## Upload to Nexus Mods

Use `tools/package-nexus.py` to repack an audited loader ZIP without rebuilding or
changing its DLL, EXE or PYD files. Set `$auditedBuildSha256` to the independently
reviewed input ZIP hash, choose a date-based `$version`, and use a fresh output directory:

```powershell
& .\.work\vendor\python-embed\python.exe .\tools\package-nexus.py `
  --runtime-zip .\release\BepInEx-Doorstop-NoPDB.zip `
  --expected-sha256 $auditedBuildSha256 `
  --version $version `
  --output-dir .\release\nexus `
  --source-url 'https://www.nexusmods.com/carxdriftracingonline2/mods/11?tab=files'
```

The packager verifies the immutable input and produces two separate downloads:

- `CarX-Drift-Racing-Online-2-BepInEx-Runtime-<version>.zip`: installable main file.
- `CarX-Drift-Racing-Online-2-BepInEx-Sources-<version>.zip`: matching corresponding
  source and build instructions; upload beside the runtime as a miscellaneous file.

Both retain licenses and notices and contain no nested archives. The runtime flattens
Python's standard library and records the source companion's filename, hash and download
page. Keep equivalent access to that exact source beside every redistributed runtime.
Review `nexus-package-verification.json`, checksums and runtime checks before upload,
then wait for Nexus's analysis. Report actual scan results; a completed scan or low
detection count does not establish safety or confirm a false positive.

## License scope

Original integration code, scripts, tests and documentation are MIT licensed.
Commercial distribution must also retain upstream LGPL terms, corresponding source
and replacement rights. A software license does not grant rights to proprietary game
content or brands. Update the notices, exact source snapshots and
checksum manifest when changing dependencies; `prepare-licenses.py` rejects changed
notice/source bytes. Do not label the whole bundle MIT or remove upstream licenses.
