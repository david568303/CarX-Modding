# Building the runtime

The Windows x64 runtime uses Doorstop for native API discovery and a .NET
bootstrap for metadata normalization. The source build uses PowerShell 7,
installed Visual Studio x64 C++ tools, CMake and a .NET SDK that targets .NET 6.

## Startup sequence

1. Doorstop discovers the aliases used by Unity's loader and checks each one
   against the loaded GameAssembly. It uses the validated map in memory and
   publishes a copy for the metadata bootstrap. Its decoder is
   `BepInEx/core/CarX.Capstone.dll`.
2. After Unity's native initialization, the managed bootstrap checks the
   installed metadata against the paired binaries. It validates the decoded
   tables and checks the input hashes again before publishing the cache.
3. The bootstrap hands control to the stock BepInEx preloader. On later
   launches it reuses the metadata only when the input and output hashes match.

## Build

Clone the source with submodules and run:

```powershell
git clone --recurse-submodules https://github.com/david568303/CarX-Modding.git
cd CarX-Modding
.\tools\build-release.ps1 -Version 2.0.0
```

Use the release tag to reproduce a specific release. The source exporter
requires a clean Git checkout and the exact pinned Doorstop submodule. The
release ZIP excludes build tools, source archives and game files. It includes
licenses, a file hash manifest and links to the exact corresponding sources.

The build obtains the pinned [BepInEx 6.0.0-be.791 Windows x64 release](https://builds.bepinex.dev/projects/bepinex_be/791/BepInEx-Unity.IL2CPP-win-x64-6.0.0-be.791%2Bb782da4.zip)
and rebuilds the following parts:

| Component | Input |
| --- | --- |
| UnityDoorstop and native API discovery | Git submodule at src/Doorstop |
| Managed metadata bootstrap | src/MetadataBootstrap, using Iced from BepInEx |
| Il2CppInterop.Common | [Il2CppInterop dbda1cb](https://github.com/BepInEx/Il2CppInterop/tree/dbda1cb353b0f4253345dc45136d170b9e50a5a0) |
| Capstone 5.0.9 | [Capstone 0225758](https://github.com/capstone-engine/capstone/tree/022575848782a4801fd150fdbc927effcbca0864), with the patches under patches/capstone |
| Dobby 1.0.5 | [Dobby 888d971](https://github.com/BepInEx/Dobby/tree/888d971214900374edbca6206fad6ded8a2c1311), with the build files under patches/dobby |

Each dependency builder checks its input and records the output SHA-256
and compiler in its build report. Use the same Capstone release headers
for compiling Doorstop. Native linker output may vary across toolchains.

For verification against the previous release, the build script can
take -ReviewedRuntimeZip with the exact 2026.11.07.2 archive and
-CapstoneIncludeDir pointing to the matching 5.0.9 include directory.
In that mode it reuses just the verified Capstone, Dobby and Common DLLs.
Doorstop and the metadata bootstrap are still rebuilt from current source.

See [testing](TESTING.md) and [publishing](PUBLISHING.md).
