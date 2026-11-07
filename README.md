# CarX Drift Racing Online 2 — UnityDoorstop & BepInEx Fix

Loader compatibility fixes for **CarX Drift Racing Online 2 (Steam, Windows x64)**.
Includes the loader, compatibility tools, and build and test sources.

## Downloads

Download installable ZIPs from [Releases](https://github.com/david568303/CarX-Modding/releases).
Extract the loader ZIP beside `CarX Drift Racing Online 2.exe`, then launch through Steam.
The first start can take several minutes to generate interop assemblies.
The loader discovers native API aliases and normalizes supported metadata for
BepInEx 6 Unity IL2CPP x64. Setup requires only the game and the ZIP.
Install compatible plugins in `BepInEx/plugins`.
The release also provides a complete source ZIP, licenses and SHA-256 checksums.

## Repositories

- [UnityDoorstop fork](https://github.com/david568303/UnityDoorstop): native loader changes,
  original upstream ancestry and LGPL license.
- This repository: the managed metadata bootstrap, tests and release packaging.
  `src/Doorstop` pins the native loader and API discovery implementation.

There is no separate release-only repository. Each release contains the loader ZIP,
licenses, checksums and corresponding source. A submodule is a pinned Git dependency;
GitHub's automatic source ZIP alone does not expand it. Use our complete source asset
or clone recursively.

## Build

```powershell
git clone --recurse-submodules https://github.com/david568303/CarX-Modding.git
cd CarX-Modding
.\tools\build-release.ps1 -Version 2026.11.07.4
```

Use PowerShell 7, existing Visual Studio C++ x64 build tools, CMake, and a .NET SDK
that can target .NET 6. The release builder checks the hashes of its pinned inputs.
Python is used only by developer reference tests.
See [third-party notices](THIRD-PARTY-NOTICES.md) for exact dependency versions and source.
See [source-built DLLs and runtime packaging](docs/SOURCE-BUILDS.md) for the reviewed source-build profile.

Original game binaries, metadata and generated interop assemblies are not distributed
in the repository or release assets.

## Compatibility and verification

The loader discovers and validates API assignments from the paired native game binaries.
The normalizer currently
supports recognized metadata schemas 38 and 39; a new schema or obfuscator redesign may
require further implementation.

Local checks cover API discovery, map validation, cache publication, metadata handling
and bootstrap behavior. Native regression tests use synthetic fixture DLLs.

Public CI runs tests that need no proprietary game files. Private-fixture tests report
skips when their inputs are absent; the full game-based checks are local-only.
See [testing instructions](docs/TESTING.md).

## Licensing and commercial use

Original integration code, scripts, tests and documentation are offered under [MIT](LICENSE).
Upstream components retain their own licenses: notably UnityDoorstop/BepInEx under
LGPL 2.1 and Il2CppInterop under LGPL 3. Their license, notice and corresponding-source
requirements still apply when redistributing them, including commercially.
MIT does not relicense third-party components or grant rights in CarX brands,
Unity SDK material or the proprietary game. This project is unofficial.
See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) and [licenses/](licenses/).

## Maintained layout

- `src/MetadataBootstrap`: managed metadata discovery and normalization.
- `src/ApiResolver`, `src/MetadataNormalizer`: reference implementations for testing.
- `src/Doorstop`: pinned upstream-history fork.
- `tests`, `tools`: relevant tests and build/package commands.
- `.work`, `release`: ignored dependencies, private test inputs and generated outputs.

Release assets exclude private game inputs, generated metadata and interop, and logs.
