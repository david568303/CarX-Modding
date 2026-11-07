# Rebuilding the four source-built DLLs

The `2026.11.07.2` runtime profile replaces UnityDoorstop's `winhttp.dll`,
`Il2CppInterop.Common.dll`, the Capstone native DLL and `BepInEx/core/dobby.dll`.
The other 248 DLL/EXE/PYD
files remain unchanged from the audited runtime. This page describes their source
builds and the separate, strict release-packaging step.

Use the maintained root revision recorded in the runtime's `SOURCE-DOWNLOADS.txt`.
For a Git checkout, initialize its pinned native dependency:

```powershell
git submodule update --init --recursive
```

For downloaded source snapshots, place the complete UnityDoorstop snapshot at
`src/Doorstop`; GitHub's root source archive does not expand submodules. Building
the DLLs works from these snapshots, while release packaging additionally requires
a clean Git checkout with its source commits pushed to the expected public repos.

## Tools and source pins

Use PowerShell 7 and existing Visual Studio 2026 C++ x64 tools, including MASM,
the Windows SDK resource compiler and NMake. Capstone and Dobby also need an existing
CMake executable; `-CMakePath` can select it explicitly. The Common build was
verified with the installed .NET SDK **10.0.402**. Packaging uses an existing
Python 3.10 or newer and its standard library. The bundled Python 3.14 is suitable.
These helpers install no compiler, SDK or system runtime. Normal .NET package
restore and pinned source downloads may use the network.

| Component | Exact public source revision | Source archive SHA-256 |
| --- | --- | --- |
| Modified UnityDoorstop | [`7316db427ac7cbc5962cbfa5046de7a342345ee6`](https://github.com/david568303/UnityDoorstop/tree/7316db427ac7cbc5962cbfa5046de7a342345ee6) | Native submodule pinned by the maintained root commit |
| Il2CppInterop 1.5.3 | [`dbda1cb353b0f4253345dc45136d170b9e50a5a0`](https://github.com/BepInEx/Il2CppInterop/tree/dbda1cb353b0f4253345dc45136d170b9e50a5a0) | `96d223a475c885ef08118a3adaee0c2ed5d65edd83fbea9987e5a305f1123ac5` |
| Capstone 5.0.9 | [`022575848782a4801fd150fdbc927effcbca0864`](https://github.com/capstone-engine/capstone/tree/022575848782a4801fd150fdbc927effcbca0864) | `eafc74835ab22d9745b29d4535c1723d6e0ddb79df840cf2f41125de9a441233` |
| Dobby 1.0.5 (BepInEx fork) | [`888d971214900374edbca6206fad6ded8a2c1311`](https://github.com/BepInEx/Dobby/tree/888d971214900374edbca6206fad6ded8a2c1311) | `00c0a582fc69efd52aa3a95449d27882384b653eb0e6524b79e796e8a8ef807d` |

No proprietary game inputs, external PDBs, symbol servers or signing key are
needed to build these DLLs. Builds stay under `.work`; they do not modify or
launch the game. Retain the upstream licenses, maintained patches and MSVC
notices listed in `licenses/source-build-notices.json` when redistributing.

## Build commands

Run these commands from the maintained repository root. Common's build directory
must not exist yet; Capstone's and Dobby's must be new or empty. Keep Dobby's
directory short: its MSVC nested includes must remain below the Windows
260-character path limit. The helper rejects an excessively long `-BuildRoot`.

```powershell
New-Item -ItemType Directory -Path .work/source-build-inputs -Force | Out-Null
Invoke-WebRequest -Uri 'https://codeload.github.com/BepInEx/Il2CppInterop/zip/dbda1cb353b0f4253345dc45136d170b9e50a5a0' -OutFile '.work/source-build-inputs/Il2CppInterop-dbda1cb.zip'

pwsh -File .\tools\build-doorstop.ps1 -Release
pwsh -File .\tools\build-il2cpp-common.ps1 -SourceZip '.work/source-build-inputs/Il2CppInterop-dbda1cb.zip' -BuildRoot '.work/build/common-source-review'
pwsh -File .\tools\build-capstone.ps1 -BuildRoot '.work/build/capstone-source-review'
pwsh -File .\tools\build-dobby.ps1 -BuildRoot '.work/dobby'
```

The Capstone and Dobby helpers download their pinned source archives if absent. To use an
already downloaded exact archive, add `-SourceArchive 'path/to/archive.zip'`.
Upstream archive checksums, the maintained Capstone patch and both helpers'
resource/integration checksums are checked before compilation. Common can instead read its exact
upstream source from the original audited runtime using `-RuntimeZip` in place
of `-SourceZip`.

| Build | DLL output | Build record |
| --- | --- | --- |
| UnityDoorstop | `.work/build/doorstop-x64/winhttp.dll` | `.work/build/doorstop-x64/build-result.json` |
| Common | `.work/build/common-source-review/candidate/Il2CppInterop.Common.dll` | `.work/build/common-source-review/build-record.json` |
| Capstone | `.work/build/capstone-source-review/native/capstone.dll` | `.work/build/capstone-source-review/build-provenance.json` |
| Dobby | `.work/dobby/native/dobby.dll` | `.work/dobby/build-provenance.json` |

UnityDoorstop uses standard static MSVC CRT startup, private names for its custom
CRT helpers, stack protection and restored version resources. The upstream
proxy exports and compatibility logic remain in the pinned fork.

Common compiles the unchanged upstream C# project in Release/netstandard2.0.
The helper changes only the isolated source tree's SDK selection from
`latestFeature` to `latestMajor`, records the selected SDK and verifies the other
upstream source files. Debug information is embedded; no external PDB is needed.

Capstone includes the maintained encoding-size initialization fix, truthful
Windows version resources and the checked-in MSVC security integration. All
architectures, detail data, x86 syntax options and allocator callbacks are
retained. Its native version is 5.0.9; the compatible Python bindings remain
5.0.6 and are identified separately in the package notices.

Dobby builds the unchanged runtime source from the pinned BepInEx fork with its
official Windows release settings: shared x64 Release, near-branch support on,
dynamic instrumentation and symbol resolution off, and obfuscation off. All
seven exports and the two-phase prepare/commit API are retained. The maintained
`patches/dobby/1.0.5-version.rc` and `1.0.5-msvc-provenance.cmake` add truthful
version/source metadata, stack
protection, CFG, ASLR, DEP and high-entropy ASLR with normal static `/MT` CRT
startup. No CET-compatible flag or runtime correctness patch is added.

The Dobby helper verifies that the source archive has no Git metadata and scopes
Git discovery during configuration/build, restoring the caller's environment.
An enclosing CarX checkout therefore cannot supply its commit as Dobby's source
version. The complete Dobby revision is recorded in VERSIONINFO and provenance.
Keep its existing Apache notice, `Dobby-LLVM-exception-NOTICE.txt` and
`Dobby-MSVC-2026-CRT-NOTICE.txt`, alongside the shared MSVC terms, as specified
in `licenses/source-build-notices.json`.

## Reviewed binary bytes and rebuild limits

These are the exact DLLs accepted by the release-packaging profile:

| DLL | SHA-256 |
| --- | --- |
| `winhttp.dll` | `722170e9d492f75f16ada1068eabdcdc06ed2fbe90154d2ceca5832562ef1588` |
| `Il2CppInterop.Common.dll` | `1928f201590f2e2b6827adba98191d253e5074769e93405a20f254e4efa984e6` |
| `capstone.dll` | `af3a1ae919c7ba700c42e5f133ffa022dfa3f05fa79672865c790243e769e727` |
| `dobby.dll` | `fac2aa3399e8b73352181bfaa5fb9e3f55eb4ebf638d35c04a0857e5bc764001` |

Doorstop and Common reproduced these hashes using the tested tools. Capstone
retains ordinary linker timestamps: its independent helper rebuild differed in
three timestamp fields while the remaining bytes, including executable code,
resources and security metadata, matched.

The packaged Dobby is the original scanned `fac2aa33...764001` artifact. A fresh
build with the checked-in helper under the real repository produced
`805ef9801bfda47324d90728ce845286295e3902da9918d961766c17f14cc6be`.
All 194 changed bytes were accounted for: 190 bytes in five absolute source-path
diagnostic strings and four linker-timestamp bytes. Executable code, version
resources, load configuration, security metadata, exports/ordinals/RVAs and all
other bytes matched. Its version string remained `Dobby-20261107`, without a
parent repository commit. The original scanned artifact was retained for packaging.

Byte-identical output across build locations, times or toolchains is therefore
**not promised**. Retain build records and
verify source/code correspondence, exports, ABI and behavior for a new build.
An antivirus result for the listed bytes does not establish a result for a
different rebuild.

## Reconstruct the audited runtime base from public assets

The original audited runtime and its corresponding source are existing assets
of [v2026.10.28.1](https://github.com/david568303/CarX-Modding/releases/tag/v2026.10.28.1):

| Asset | SHA-256 |
| --- | --- |
| [`BepInEx-Doorstop-NoPDB.zip`](https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/BepInEx-Doorstop-NoPDB.zip) | `e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e` |
| [`CarX-Modding-Source-2026.10.28.1.zip`](https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/CarX-Modding-Source-2026.10.28.1.zip) | `8b1d49f2d756ef90cd791bc536b87d9209cf8c5519ef9babc270b42e7639bae0` |

Save those files under `.work/source-build-inputs`. The unchanged
`tools/package-nexus.py` verifies both assets and their source/license records:

```powershell
python -B .\tools\package-nexus.py `
  --runtime-zip '.work/source-build-inputs/BepInEx-Doorstop-NoPDB.zip' `
  --expected-sha256 'e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e' `
  --source-zip '.work/source-build-inputs/CarX-Modding-Source-2026.10.28.1.zip' `
  --source-sha256 '8b1d49f2d756ef90cd791bc536b87d9209cf8c5519ef9babc270b42e7639bae0' `
  --source-url 'https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/CarX-Modding-Source-2026.10.28.1.zip' `
  --version '2026.11.05.2' --output-dir '.work/reconstructed-runtime-base'
```

The historical base ZIP hash is
`fb5be7816afe5489699c65ef19a92806e2cf2a06a0cf603716ff04c17414aa63`.
A reconstruction can differ in ZIP container metadata and the package manifest's
`createdUtc`. The source-build packager also accepts a canonical-equivalent base:
it verifies every uncompressed path and payload plus all manifest content,
ignoring only ZIP container metadata and a valid UTC `createdUtc` value. Changed
payloads, licenses, provenance or version are rejected.

## Package the reviewed release

`tools/package-av-workaround.py` accepts only the four reviewed hashes above,
the audited or canonical-equivalent base, the pinned native Git revision and
the committed source-build notices. Root and native working trees must be clean, with
their exact commits pushed to the expected public GitHub repositories. Output
directories must be fresh or empty.

For this exact profile, place the four accepted DLLs from the reviewed runtime
under `.work/accepted-runtime`, retaining their runtime paths, then run:

```powershell
python -B .\tools\package-av-workaround.py `
  --base-zip '.work/reconstructed-runtime-base/CarX-Drift-Racing-Online-2-BepInEx-Runtime-2026.11.05.2.zip' `
  --winhttp '.work/accepted-runtime/winhttp.dll' `
  --common '.work/accepted-runtime/BepInEx/core/Il2CppInterop.Common.dll' `
  --capstone '.work/accepted-runtime/BepInEx/compatibility/python/Lib/site-packages/capstone/lib/capstone.dll' `
  --dobby '.work/accepted-runtime/BepInEx/core/dobby.dll' `
  --output-dir '.work/source-build-release' --version '2026.11.07.2'
```

An independent Capstone or Dobby rebuild with different linker timestamps or
source-path strings will fail this exact-binary profile. Publishing new bytes requires their own compatibility
checks, scan and deliberate profile update on an isolated branch.

The output is one installable runtime ZIP, checksum files and a verification
report. It contains licenses and immutable GitHub source links; source archives,
development trees, proprietary game inputs and custom cars are excluded. Only
the runtime ZIP belongs on Nexus. The source remains available on GitHub.
