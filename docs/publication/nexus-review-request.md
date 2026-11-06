# DRAFT — not submitted

To: support@nexusmods.com  
Subject: Review request — CarX Drift Racing Online 2 loader, file 12

Please review the quarantined installable Windows x64 loader on
[this mod page](https://www.nexusmods.com/carxdriftracingonline2/mods/11?tab=files&file_id=12).
File **12**, version **2026.11.05.1**, is
`CarX-Drift-Racing-Online-2-BepInEx-Runtime-2026.11.05.1.zip`.
SHA-256: `0ad6f585f5ebb2d044a3d5f873218a9fb4b4ff24d1a1168ef60a61c2ef76e964`.

The notice lists executable types, scanner detections and nested archives as
possible causes. This ZIP contains **no nested archives**: Python's standard
library was expanded and its isolated import path adjusted. All 252 executable
files are unchanged from the audited input build. Please identify the concrete
failing check and review whether this file can be released.

Relevant VirusTotal reports:

- [Whole ZIP](https://www.virustotal.com/gui/file/0ad6f585f5ebb2d044a3d5f873218a9fb4b4ff24d1a1168ef60a61c2ef76e964/detection): latest 5 November report is 0/41, but VBA32 and many other engines timed out. Its earlier completed report was 1/63, VBA32 `TScope.Trojan.MSIL`; the timeout does not establish correction.
- [Modified winhttp.dll](https://www.virustotal.com/gui/file/0a7b1228b8122633aca507b2b7ead809ebf30bc9d7cc527479d389794eed24e6/detection): completed 7 November, Cynet `Malicious (score: 100)`, 1/71.
- [Il2CppInterop.Common.dll](https://www.virustotal.com/gui/file/070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f/detection): completed 7 November, VBA32 `TScope.Trojan.MSIL`, 1/70; byte-identical to official BepInEx be.791.
- [Capstone DLL](https://www.virustotal.com/gui/file/651096794b3c3c2a1df24345e22844a0311fca56a4f74ea1cfa29107983760e1/detection): completed 7 November, Cynet `Malicious (score: 100)`, 1/70; byte-identical to the official Capstone 5.0.6 Windows wheel.

These are suspected false positives, not vendor-confirmed clearances or a safety
guarantee. The quarantine notice does not establish which detection caused it.

Source and reproduction:

1. Download the [explicit complete GitHub source asset](https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/CarX-Modding-Source-2026.10.28.1.zip), which expands the Doorstop submodule. Compiled project revision:
   `bd21c6483e89d38ff5faa77e256c1046510004a9`; native revision:
   `ad3edbebd071449c22845c18a12326d49a437c89`.
2. Extract it and run [tools/build.ps1](https://github.com/david568303/CarX-Modding/blob/bd21c6483e89d38ff5faa77e256c1046510004a9/tools/build.ps1) in PowerShell 7 with existing Visual Studio C++ x64 tools and a .NET SDK. It provisions checksum-pinned runtime dependencies and builds native Doorstop plus the managed bootstrap; it installs no compiler. [Build/package instructions](https://github.com/david568303/CarX-Modding/blob/bd21c6483e89d38ff5faa77e256c1046510004a9/docs/PUBLISHING.md).
3. To reproduce the Nexus layout separately, clone `CarX-Modding` recursively at **b92f120** and run [that revision's exact first Nexus packager](https://github.com/david568303/CarX-Modding/blob/b92f120bde985a1db4b22f11e8002127759c1689/tools/package-nexus.py). Pass `--runtime-zip` the [existing GitHub runtime](https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/BepInEx-Doorstop-NoPDB.zip), `--expected-sha256 e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e`, `--version 2026.11.05.1`, and `--output-dir` a fresh directory. Only its Runtime ZIP is under review. Rebuilding may produce different hashes; the input hash and preserved member bytes provide provenance.

Source remains available on GitHub; no source upload to Nexus is requested.
