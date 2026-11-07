# Third-party notices and license scope

Original compatibility scripts, managed bootstrap, build tools, tests and
documentation use the [MIT license](LICENSE), copyright (c) 2026 David Salas Kalendar.
MIT permits commercial use and sale, subject to retaining its notice.
This grant covers only rights in our own work. The following components retain
their original licenses; including them together does not relicense them as MIT.

## Included components

The installable runtime includes the components below and retains their notices.

| Component | Shipped version / source revision | License | Full text | Applies to |
| --- | --- | --- | --- | --- |
| UnityDoorstop | 4.6.0 / modified fork from 1c3ece1 | LGPL-2.1-only | [UnityDoorstop-LGPL-2.1.txt](licenses/UnityDoorstop-LGPL-2.1.txt) | loader |
| BepInEx | 6.0.0-be.791+b782da4 | LGPL-2.1-only | [BepInEx-LGPL-2.1.txt](licenses/BepInEx-LGPL-2.1.txt) | loader |
| Il2CppInterop | 1.5.3+dbda1cb | LGPL-3.0-only | [Il2CppInterop-LGPL-3.0-and-GPL-3.0.txt](licenses/Il2CppInterop-LGPL-3.0-and-GPL-3.0.txt) | loader |
| HarmonyX | 2.10.2 | MIT | [HarmonyX-MIT.txt](licenses/HarmonyX-MIT.txt) | loader |
| AsmResolver family | 6.0.0-beta.5+124e161 | MIT | [AsmResolver-MIT.txt](licenses/AsmResolver-MIT.txt) | loader |
| AssetRipper.CIL | 1.2.2+06216e6 | MIT | [AssetRipper.CIL-MIT.txt](licenses/AssetRipper.CIL-MIT.txt) | loader |
| AssetRipper.Primitives | 3.2.0+d759b3d | MIT | [AssetRipper.Primitives-MIT.txt](licenses/AssetRipper.Primitives-MIT.txt) | loader |
| uTinyRipper portions in AssetRipper.Primitives | upstream notice | MIT | [AssetRipper.Primitives-uTinyRipper-MIT.txt](licenses/AssetRipper.Primitives-uTinyRipper-MIT.txt) | loader |
| Cpp2IL, LibCpp2IL, StableNameDotNet, WasmDisassembler | development.1452+558ddd9 | MIT | [Cpp2IL-MIT.txt](licenses/Cpp2IL-MIT.txt) | loader |
| Disarm | master.99+8574010 | MIT | [Disarm-MIT.txt](licenses/Disarm-MIT.txt) | loader |
| Dobby (BepInEx fork) | 1.0.5 / 888d971 | Apache-2.0 | [Dobby-Apache-2.0.txt](licenses/Dobby-Apache-2.0.txt) | loader |
| Gee.External.Capstone / Capstone.NET | 2.3.2+b90e380 | MIT | [Capstone.NET-MIT.txt](licenses/Capstone.NET-MIT.txt) | loader |
| Iced | 1.21.0+601c405 | MIT | [Iced-MIT.txt](licenses/Iced-MIT.txt) | loader |
| Mono.Cecil, Mdb, Pdb and Rocks | 0.11.4 | MIT | [Mono.Cecil-MIT.txt](licenses/Mono.Cecil-MIT.txt) | loader |
| MonoMod.RuntimeDetour and Utils | 22.07.31.01 | MIT | [MonoMod-MIT.txt](licenses/MonoMod-MIT.txt) | loader |
| MonoMod.Backports and ILHelpers | 1.1.2 / 1.1.0 | MIT | [MonoMod.Backports-MIT.txt](licenses/MonoMod.Backports-MIT.txt) | loader |
| SemanticVersioning | 2.0.2 | MIT | [SemanticVersioning-MIT.txt](licenses/SemanticVersioning-MIT.txt) | loader |
| .NET mini CoreCLR runtime (BepInEx fork) | 6.0.7 / e10df43 | MIT + third-party notices | [dotnet-LICENSE.txt](licenses/dotnet-LICENSE.txt) | loader |
| .NET runtime third-party notices | 6.0.7 | various; see full notice | [dotnet-THIRD-PARTY-NOTICES.txt](licenses/dotnet-THIRD-PARTY-NOTICES.txt) | loader |
| Microsoft .NET Windows runtime redistribution terms | 6.0.7 | Microsoft .NET Library terms | [dotnet-Windows-LICENSE-MSFT.txt](licenses/dotnet-Windows-LICENSE-MSFT.txt) | loader |
| Microsoft.Extensions.* and Microsoft.Bcl.AsyncInterfaces | 6.0.0+4822e3c | MIT | [Microsoft.Extensions-MIT.txt](licenses/Microsoft.Extensions-MIT.txt) | loader |
| Capstone native disassembler | 5.0.9 | BSD-3-Clause | [Capstone-BSD-3-Clause.txt](licenses/Capstone-BSD-3-Clause.txt) | loader |
| LLVM-derived portions in Capstone | 5.0.9 | NCSA / LLVM notice | [Capstone-LLVM.txt](licenses/Capstone-LLVM.txt) | loader |
| Microsoft.DiaSymReader.Native.amd64.dll | 16.9.0-beta1.21055.5 / file 14.28.29715.1 | Microsoft .NET Library terms | [Microsoft.DiaSymReader.Native-LICENSE.txt](licenses/Microsoft.DiaSymReader.Native-LICENSE.txt) | loader |

The machine-readable [license manifest](licenses/manifest.json) records each
notice's exact source URL and SHA-256 and the two bundled upstream source
archives. Versions were read from shipped DLL metadata and pinned upstream
build/package metadata; the unchanged official BepInEx archive is SHA-256
`bb1c510909b69522733791f3a0817a487379a52da6468a492f1c9c19b3ec6f9a`.
In that baseline, bundled BepInEx, Il2CppInterop and their upstream dependencies
are unchanged. The separate source-build runtime profile rebuilds modified
UnityDoorstop, unchanged Il2CppInterop.Common 1.5.3 source, and Capstone native 5.0.9
from commit `022575848782a4801fd150fdbc927effcbca0864` with the maintained correctness,
version resources and Windows protection flags. Doorstop uses the native Capstone DLL.
The follow-up profile also rebuilds Dobby 1.0.5 from unchanged runtime source
`888d971214900374edbca6206fad6ded8a2c1311`, retaining the official Windows
feature profile with version resources and compiler protections. Its compiled
LLVM clear-cache component's attribution and complete Apache 2.0 with LLVM
exception terms are retained in
[Dobby-LLVM-exception-NOTICE.txt](licenses/Dobby-LLVM-exception-NOTICE.txt).
Exact revisions, modifications and build instructions are in
[SOURCE-BUILDS.md](docs/SOURCE-BUILDS.md) and each runtime's SOURCE-DOWNLOADS.txt.

The source-built native DLLs statically link Microsoft's release C/C++ runtime.
The [MSVC runtime notice](licenses/MSVC-2026-CRT-NOTICE.txt),
[runtime terms](licenses/MSVC-2026-Runtime-LICENSE.txt) and
[Visual Studio Community terms](licenses/MSVC-2026-Community-LICENSE.txt) are retained
separately; MIT does not relicense Microsoft code. Their official provenance and
checksums are recorded in [source-build-notices.json](licenses/source-build-notices.json).
The additive [Dobby runtime notice](licenses/Dobby-MSVC-2026-CRT-NOTICE.txt)
records its static runtime; the original Microsoft notices remain unchanged.

Copyright holders include the BepInEx Team; knah and Il2CppInterop contributors;
Washi; ds5678; Sam Byass; Ahmed Garhy; iced contributors; Jb Evain and Novell;
0x0ade and DaNike; Adam Reeve; Nguyen Anh Quynh and COSEINC;
and the .NET Foundation, Microsoft and contributors.
The full texts preserve the upstream notices, including notices for bundled
LLVM, uTinyRipper, and .NET runtime portions.

## LGPL source and replacement rights

UnityDoorstop remains LGPL-2.1-only. BepInEx remains LGPL-2.1-only and
Il2CppInterop remains LGPL-3.0-only. Their licenses permit commercial distribution
when their conditions are followed. The Il2CppInterop license file also contains
the incorporated GNU GPL version 3 text.

The installable ZIP on GitHub and Nexus includes SOURCE-DOWNLOADS.txt and
[replacement instructions](licenses/SOURCE-COMPLIANCE.txt). These provide
equivalent access to complete corresponding source, including the pinned
UnityDoorstop fork, upstream dependencies and the maintained build changes.
The explicit GitHub source release asset also expands the Doorstop submodule.

Replaceable shared DLLs are used. Users may modify/rebuild the LGPL components
and replace them with interface-compatible versions. This project imposes no
restriction on reverse engineering needed to debug those modifications. Do not
remove the notices, source or replacement instructions when redistributing a
loader release. Publish the corresponding source beside any redistributed
binaries, including any further modifications you make.

## Unity, game interfaces, names and other rights

Unity and CarX game binaries, extracted game assemblies, metadata, game assets
and generated game interop are not part of this project's source or installable
loader files. Users supply their own installed game.

`src/ApiResolver/il2cpp-api-schema.json` is an interoperability description of
native API names, type signatures and declaration order. Its source URLs and
original input hashes are retained in that file. It contains no Unity function
implementations. The referenced SDK artifacts do not carry an explicit open
source license; this project does not claim to own or relicense Unity's API
definitions, headers, SDK or engine. Original schema-processing and validation
code is covered by MIT. Redistribution of a Unity SDK is outside this license.

No permission to use CarX, Unity or other trademarks, logos or trade dress
is granted by the project license. Names identify compatibility; no endorsement
is claimed. Commercial software licensing permission is not a blanket brand or
game-content commercialization permission.

## Release policy

All installable ZIPs include `LICENSE`, this notice and `licenses/`. The loader
also provides corresponding source access as described above. Source archives generated
from this repository retain the same licensing files. Large dependency archives
and generated game files stay out of Git. The runtime packager checks the
committed notice hashes and records the exact corresponding source revisions.
