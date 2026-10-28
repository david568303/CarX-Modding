# Third-party notices and license scope

Original compatibility scripts, managed bootstrap, build tools, tests and
documentation use the [MIT license](LICENSE), copyright (c) 2026 David Salas Kalendar.
MIT permits commercial use and sale, subject to retaining its notice.
This grant covers only rights in our own work. The following components retain
their original licenses; including them together does not relicense them as MIT.

## Included components

The loader ZIP includes the components below. Their original notices and
licenses are retained with the compatibility source and installable package.

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
| pefile and ordlookup | 2024.8.26 | MIT | [pefile-MIT.txt](licenses/pefile-MIT.txt) | loader |
| Capstone native disassembler and Python bindings | 5.0.6 | BSD-3-Clause | [Capstone-BSD-3-Clause.txt](licenses/Capstone-BSD-3-Clause.txt) | loader |
| LLVM-derived portions in Capstone | 5.0.6 | NCSA / LLVM notice | [Capstone-LLVM.txt](licenses/Capstone-LLVM.txt) | loader |
| Capstone Python binding notice | 5.0.6 | BSD-3-Clause | [Capstone-Python-BSD.txt](licenses/Capstone-Python-BSD.txt) | loader |
| Python embedded runtime and bundled libraries | 3.14.7 | PSF-2.0 and included third-party terms | [Python-LICENSE.txt](licenses/Python-LICENSE.txt) | loader |
| Microsoft.DiaSymReader.Native.amd64.dll | 16.9.0-beta1.21055.5 / file 14.28.29715.1 | Microsoft .NET Library terms | [Microsoft.DiaSymReader.Native-LICENSE.txt](licenses/Microsoft.DiaSymReader.Native-LICENSE.txt) | loader |

The machine-readable [license manifest](licenses/manifest.json) records each
notice's exact source URL and SHA-256 and the two bundled upstream source
archives. Versions were read from shipped DLL metadata and pinned upstream
build/package metadata; the unchanged official BepInEx archive is SHA-256
`bb1c510909b69522733791f3a0817a487379a52da6468a492f1c9c19b3ec6f9a`.
Bundled BepInEx, Il2CppInterop and their upstream dependencies are unchanged.
Only UnityDoorstop and the separate compatibility/bootstrap components were
modified or added by this project.

Copyright holders include the BepInEx Team; knah and Il2CppInterop contributors;
Washi; ds5678; Sam Byass; Ahmed Garhy; iced contributors; Jb Evain and Novell;
0x0ade and DaNike; Adam Reeve; Ero Carrera; Nguyen Anh Quynh and COSEINC;
the .NET Foundation, Microsoft and contributors; and the Python Software Foundation.
The full texts preserve the upstream notices, including notices for bundled
LLVM, uTinyRipper, .NET runtime and Python library portions.

## LGPL source and replacement rights

UnityDoorstop remains LGPL-2.1-only. BepInEx remains LGPL-2.1-only and
Il2CppInterop remains LGPL-3.0-only. Their licenses permit commercial distribution
when their conditions are followed. The Il2CppInterop license file also contains
the incorporated GNU GPL version 3 text.

Every loader ZIP contains the complete modified Doorstop and compatibility source
with build/install scripts in `BepInEx/compatibility/source.zip`. The exact
unmodified BepInEx and Il2CppInterop source snapshots for the bundled DLLs are
included in `BepInEx/compatibility/sources/`, together with their source manifest
and [replacement instructions](licenses/SOURCE-COMPLIANCE.txt). This includes
the upstream build projects and reference assemblies shipped in those source
repositories; those references are not this game's executables or extracted
game code and are not relicensed by this project.

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
also includes the corresponding source described above. Source archives generated
from this repository retain the same licensing files. Large dependency archives
and generated game files stay out of Git. `tools/prepare-licenses.py` verifies
the committed notices and retrieves only the checksum-pinned corresponding source
archives. Pass `--check-only` for an offline verification.
