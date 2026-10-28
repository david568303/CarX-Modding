# CarX Drift Racing Online 2 — UnityDoorstop & BepInEx Fix

Loader compatibility fixes for **CarX Drift Racing Online 2 (Steam, Windows x64)**.
Enables UnityDoorstop and BepInEx 6 Unity IL2CPP by discovering native API bindings
without PDB files and normalizing the game's supported metadata formats.

## Downloads

Download installable ZIPs from [Releases](https://github.com/david568303/CarX-Modding/releases).
Extract the loader ZIP beside `CarX Drift Racing Online 2.exe`, then launch through Steam.
The first start can take several minutes to generate interop assemblies.
The loader discovers native API aliases and normalizes supported metadata for
BepInEx 6 Unity IL2CPP x64. Install compatible plugins in `BepInEx/plugins`.
The release also provides a complete source ZIP, licenses and SHA-256 checksums.

## Repositories

- [UnityDoorstop fork](https://github.com/david568303/UnityDoorstop): native loader changes,
  original upstream ancestry and LGPL license.
- This repository: API discovery, metadata normalization/bootstrap, tests
  and release packaging. `src/Doorstop` is a Git submodule pinned to an exact fork commit.

There is no separate release-only repository. Each release contains the loader ZIP,
licenses, checksums and corresponding source. A submodule is a pinned Git dependency;
GitHub's automatic source ZIP alone does not expand it. Use our complete source asset
or clone recursively.

## Build

```powershell
git clone --recurse-submodules https://github.com/david568303/CarX-Modding.git
cd CarX-Modding
.\tools\build.ps1
.\tools\package.ps1
```

Use PowerShell 7, existing Visual Studio C++ x64 build tools and a .NET SDK with the
.NET 6 targeting pack. The pure test programs use the .NET 10 SDK. Scripts do not install
a compiler. Provisioning downloads pinned, hash-verified BepInEx/Python/dependency inputs.
See [third-party notices](THIRD-PARTY-NOTICES.md) for exact dependency versions and source.

Original game binaries, metadata and generated interop assemblies are not distributed
in the repository or release assets.

## Compatibility and verification

The loader discovers API assignments from the paired native game binaries and validates
canonical identities against native code evidence. It does not require PDBs, symbol
servers, stored game addresses or a table of game versions. The normalizer currently
supports recognized metadata schemas 38 and 39; a new schema or obfuscator redesign may
require further implementation.

Earlier local tests loaded BepInEx successfully after removing debug metadata from
isolated game copies and denying symbol access. Synthetic tests cover map validation,
cache publication, metadata handling and bootstrap behavior. The native resolver
suite uses synthetic fixture DLLs.

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

- `src/ApiResolver`, `src/MetadataNormalizer`, `src/MetadataBootstrap`: compatibility code.
- `src/Doorstop`: pinned upstream-history fork.
- `tests`, `tools`: relevant tests and build/package commands.
- `.work`, `release`: ignored dependencies, private test inputs and generated outputs.

Only the surviving compatibility implementation is published. Abandoned implementations,
private game inputs, generated metadata/interop and logs are excluded.
