# Antivirus review — updated 7 November 2026

The installable CarX Drift Racing Online 2 package has a suspected false positive,
not a vendor-confirmed false positive. A low detection count does not establish safety.
The previous Nexus file **15** is **quarantined and archived**. That runtime ZIP's latest
VirusTotal analysis is **1/62**, with Zillya reporting `Trojan.GenCBL.Win32.22575`
on **7 November 2026 at 02:05:52 Europe/Madrid**. The bundled, unchanged official
`dobby.dll` has the **same Zillya label** in a dated direct report and is a likely
contributor. This does not establish the sole archive trigger or a source-line cause.

## Source-build candidate and validation

Development began on `fix/nexus-release-analysis`; the additional Dobby build is
isolated on `fix/dobby-windows-build`. `main` and existing GitHub
releases are unchanged. No support request has been sent on the user's behalf.

### Dobby follow-up build

The unchanged official Dobby DLL has a matching Zillya detection, as detailed
below. Its official [1.0.5 release](https://github.com/BepInEx/Dobby/releases/tag/v1.0.5)
was downloaded independently and its x64 DLL matches the bundled SHA-256
`8015de7d867245a1095d13947a63763878e4cf5fd3d3089b63cc39200b055ded`.
This supplies a concrete dependency to investigate; it does not reveal a vendor's
rule or prove that Dobby is the sole archive trigger.

The reviewed replacement uses the same pinned runtime source and official
Windows x64 Release feature profile, with truthful version resources and ordinary
MSVC stack protection, CFG, ASLR, DEP and high-entropy address support. It retains
normal static CRT startup, all seven exports and ordinals, and the two-phase
Prepare/Commit API. No Dobby runtime source was changed, and no extra runtime
installer or DLL is required. CET compatibility is not claimed.

The exact replacement is 212,480 bytes, SHA-256
`fac2aa3399e8b73352181bfaa5fb9e3f55eb4ebf638d35c04a0857e5bc764001`.
Its [completed direct report](https://www.virustotal.com/gui/file/fac2aa3399e8b73352181bfaa5fb9e3f55eb4ebf638d35c04a0857e5bc764001/detection)
shows **0/71**, analysed **7 November 2026 at 02:54:54 Europe/Madrid**.
Zillya, Cynet, SecureAge, Microsoft and VBA32 explicitly returned `Undetected`.
The other three replacement reports were reopened and still showed 0/71 with
these vendors `Undetected`; their analysis dates remain the dated times below.
These observations apply to the exact DLL bytes and do not establish the final
archive result or future verdicts.

The [source-only Dobby comparison suite](../tests/DobbyCompatibility/README.md)
ran against both the original and replacement: **11/13 native cases passed on
each**, and **4/4 actual BepInEx wrapper cases passed on each** using bundled
CoreCLR 6.0.7. No new regressions or other behavior mismatches were detected in
the exercised cases; all 925 runtime inputs remained unchanged. Both DLLs retain
the same two native correctness failures: pinned Dobby widens a short conditional
branch without correcting for the four-byte length change. Generated branch
targets and trampoline bytes match between builds. The suite honestly exits 1
for these existing failures. This build does not repair that upstream runtime
bug, and these synthetic checks do not establish universal plugin compatibility
or replace an in-game test.

The `2026.11.07.2` package profile replaces four DLLs and retains the other 248
executable files. It adds the LLVM clear-cache attribution/exception license and
a Dobby MSVC runtime notice while preserving every existing license. The build
helper, source pins and reproducibility limits are recorded in
[SOURCE-BUILDS.md](SOURCE-BUILDS.md).

The final ZIP is `CarX-Drift-Racing-Online-2-BepInEx-Runtime-2026.11.07.2.zip`,
48,124,156 bytes, SHA-256
`6a308327941689f6899a73dc2592ffa8738298582e0a4ea445a723f9c671da59`.
Its [completed archive report](https://www.virustotal.com/gui/file/6a308327941689f6899a73dc2592ffa8738298582e0a4ea445a723f9c671da59/detection)
shows **0/60**, analysed **7 November 2026 at 03:16:26 Europe/Madrid**.
Zillya, Cynet, Microsoft and VBA32 explicitly returned `Undetected`. ClamAV timed
out; eight engines failed and six could not process the file type. Those are
not clean verdicts. VirusTotal also warned that the multi-file ZIP exceeds its
3 MB archive-inspection limit. This archive result and the four direct DLL
reports describe different coverage; neither guarantees future vendor results.
This exact ZIP was published as Nexus **file 16**, version **2026.11.07.2**, on
**7 November 2026 at 03:20 Europe/Madrid**. File 15 was archived; only the built
runtime is a Main/Primary download. The public description and changelog both
read: "Rebuilt Dobby with Windows version metadata and security protections to
address antivirus detections." Nexus's independent scan is still in progress
at this observation; VirusTotal's report does not establish Nexus availability.

An independent ZIP audit hashed all 927 files and 926 manifest records, verified
the four exact DLLs and 248 unchanged executable files, all existing license bytes,
the two added Dobby notices, wheel RECORD and six immutable source snapshots.
Fresh extraction passed isolated bundled-Python imports and Capstone decoding
from an unrelated directory. All 927 extracted file hashes remained unchanged.

### Previously reviewed three-DLL build

Two replacement DLLs completed direct scans on **7 November 2026 at 01:08:29
Europe/Madrid**, each at **0/71**. Cynet, Microsoft and VBA32 explicitly returned
`Undetected` in both reports. These are dated observations, not fresh checks of
the current Zillya detection or guarantees of future scanner verdicts:

| Component | Source/build change | Completed report |
| --- | --- | --- |
| UnityDoorstop `winhttp.dll` | Standard static MSVC runtime startup, stack protection, privately named custom CRT helpers, truthful version resources, and defined file-I/O results; existing loader/discovery behavior retained | [722170e9…](https://www.virustotal.com/gui/file/722170e9d492f75f16ada1068eabdcdc06ed2fbe90154d2ceca5832562ef1588/detection) |
| `Il2CppInterop.Common.dll` | Unchanged upstream 1.5.3 C# source rebuilt with the installed SDK and deterministic upstream project settings | [1928f201…](https://www.virustotal.com/gui/file/1928f201590f2e2b6827adba98191d253e5074769e93405a20f254e4efa984e6/detection) |

The third replacement, Capstone native **5.0.9**, completed at **0/71** on 7 November
at **01:38:27 Europe/Madrid**, with Cynet, Microsoft and VBA32 explicitly
`Undetected`: [af3a1ae9…](https://www.virustotal.com/gui/file/af3a1ae919c7ba700c42e5f133ffa022dfa3f05fa79672865c790243e769e727/detection).
It uses the current maintenance source, a defined immediate-size output on lookup
miss, truthful Windows version resources, stack protection, CFG, ASLR/DEP and CET
compatibility. All architectures, detailed decoding and allocator callbacks remain
enabled. Its full API/header layout and all 20 exports/ordinals match official 5.0.9;
9,270 decoding cases, 167,424 instruction-detail records and 23 upstream examples
match that release. Custom allocator and skip-data callbacks also pass with CFG.
The upstream 5.0.9 BSD/LLVM/Python license texts are byte-identical to the retained
5.0.6 notices. The unchanged Python bindings remain version 5.0.6; the native version
is disclosed separately in package provenance.

The native fork revision is
[`7316db427ac7cbc5962cbfa5046de7a342345ee6`](https://github.com/david568303/UnityDoorstop/commit/7316db427ac7cbc5962cbfa5046de7a342345ee6).
Its rebuilt DLL preserves all 87 exports and ordinals. Synthetic host tests passed
110 forwarding/load/unload/rebase checks and 57 enabled import-hook checks against
both original and rebuilt loaders, without invoking the game or CoreCLR.
Common preserves 500 checked public API/layout/attribute contracts and its assembly
identity/references; 16 behavioral checks passed for each build using the bundled
CoreCLR 6.0.7. Independent source builds reproduced both scanned hashes. Embedded
managed debug information does not require external PDB files.

Earlier Capstone candidates were rejected. A complete 5.0.6 source build with an immediate-size
initialization correctness patch passed the full comparison corpus but still
received [1/71 from Cynet](https://www.virustotal.com/gui/file/efba1c5bd1c702007306d09b575b861bbbffec54e53eee27ec3840180748988f/detection).
The unmodified official 5.0.9 Windows DLL also completed at
[1/71 from Cynet](https://www.virustotal.com/gui/file/76958e18380023a68fd1714fa2e01c594cc6db1955a07ad6937b66e66dc5d6c3/detection)
on 7 November at 01:27:37 Europe/Madrid. Neither is shipped in the workaround.
The ordinary Nexus packager is unchanged; a separate source-build profile pins the
three tested replacements, updates the wheel RECORD and package manifest, preserves
the other 249 executable files and existing licenses, and adds MSVC runtime terms.

The final three DLLs passed **42 integration tests with zero skips**. Fresh discovery
and metadata normalization against each of two preserved native-input fixtures
produced the same 234 API bindings and expected normalized hashes. An independent
LibCpp2IL parser checked the metadata table counts and 425,524 / 450,872 names.
PDB/DIA/symbol access was denied in all four cold pipeline processes, with zero
attempts. All six original inputs and all staged runtime files remained unchanged.
These checks did not start the actual game and do not replace an in-game test.

The final installable runtime is
`CarX-Drift-Racing-Online-2-BepInEx-Runtime-2026.11.07.1.zip`, 48,112,884 bytes,
SHA-256 `7ba02488cc945fb7ff99403e498568cdc77d43ca7827f7316b0c33293a1e8991`.
Its [latest archive report](https://www.virustotal.com/gui/file/7ba02488cc945fb7ff99403e498568cdc77d43ca7827f7316b0c33293a1e8991/detection)
is **1/62**, analysed 7 November at **02:05:52 Europe/Madrid**. Zillya reports
`Trojan.GenCBL.Win32.22575`; Cynet, Microsoft and VBA32 return `Undetected`.
This supersedes the earlier **0/65** observation at **01:51:42 Europe/Madrid**.
In that earlier report ClamAV timed out, ALYac and Trustlook failed, and seven engines
could not process the archive type; it is retained as history, not current clearance.
VirusTotal warned that this multi-file archive exceeds its 3 MB archive-inspection
limit. Its Details page lists **927 entries**, **252 PE files** and a contains-PE
warning. No `no_nested` tag was observed; the absence of nested archives is a
separate result of the local ZIP audit.
The fully expanded Relations listing shows 198 rows: 197 linked reports display
zero detections; the package manifest has no linked report. All 197 linked names
and hashes match this ZIP, but they cover only **100 of its 252 PE files**, with
Scanned dates ranging from **18 January to 7 November 2026** and 47–72 engines.
Common, Il2CppInterop.Runtime and MonoMod.RuntimeDetour appear; the rebuilt
winhttp/Capstone, dobby and MetadataBootstrap do not appear in this listing.
These are heterogeneous historical report summaries, not a fresh uniform scan of
all 925 files. Dobby is absent from that Relations listing but has a separately
opened, positive direct report, described below. The archive result is separate
from the dated direct reports for the replacement DLLs.

The bundled **`BepInEx/core/dobby.dll`**, 205,312 bytes, SHA-256
`8015de7d867245a1095d13947a63763878e4cf5fd3d3089b63cc39200b055ded`,
is byte-for-byte identical to the official BepInEx 791 dependency. Its
[direct report](https://www.virustotal.com/gui/file/8015de7d867245a1095d13947a63763878e4cf5fd3d3089b63cc39200b055ded/detection)
shows **3/71**, last analysed **1 November 2026 at 10:34:36 Europe/Madrid**:
Zillya `Trojan.GenCBL.Win32.22575`, Cynet `Malicious (score: 100)` and SecureAge
`Malicious`. The exact Zillya label matches the archive's later result, making this
a likely contributor; it does not prove Dobby is the only archive trigger, that its
source is malicious, or that a particular source line causes the detection. This is
a historical direct report. A fresh reanalysis completed on **7 November 2026 at
02:43:27 Europe/Madrid**, showing **2/69**: Cynet `Malicious (score: 100)` and
SecureAge `Malicious` persist. Zillya returned **Failure**, not `Undetected`;
Microsoft and VBA32 returned `Undetected`. Zillya's failed fresh check does not
clear or invalidate its earlier matching detection, or establish Dobby as the sole
archive trigger.

Independent final-ZIP verification checked all 925 files and 924 manifest records,
all three exact scanned hashes, 249 unchanged executable files, the 29 preserved
license files, three added MSVC notices, the wheel RECORD and immutable source
links. Fresh extraction passed isolated Python imports and decoding from an
unrelated working directory, with all runtime files remaining unchanged.

A subsequent read-only audit found no duplicate or case-colliding member names,
encrypted entries, header/CRC mismatches, overlapping entries, prefix/trailing data,
nested archives or unexplained PE overlays. All 249 unchanged executables retain
their audited bytes: 215 match the official BepInEx distribution, 33 match the
official Python embedded distribution, and one is the existing MetadataBootstrap.
All 217 certificate-bearing executables have valid Authenticode signatures; the
other 35 are unsigned. These observations do not identify Zillya's rule or certify
the package; they provide no evidence of a packaging anomaly to repair.

This exact ZIP is now uploaded to Nexus as **file 15**, version **2026.11.07.1**:
[current Nexus file](https://www.nexusmods.com/carxdriftracingonline2/mods/11?tab=files&file_id=15).
The public page records **7 November 2026, 02:05 Europe/Madrid**, with a displayed
size of **45.9 MB**. File 15 is now **quarantined**, with the public header
**“Some suspicious files”**. Its generic quarantine notice lists executable file
types, scanner detections and nested archives as possible reasons; it does not
identify the failing check or member. Nexus's restriction and the VirusTotal
archive report are separate observations. The earlier pending-scan message has
been superseded; Nexus has not cleared the file.
Previous runtime file **12** was archived, leaving only this runtime in Main Files.
No source archive was uploaded, and no support message was sent.

The saved Nexus changelog and visible file description both read:

> Rebuilt Doorstop and Common, and updated Capstone to address antivirus false positives.

These results show which exact builds receive different scanner verdicts. They do
not reveal either vendor's private detection rule or establish a particular source
line as its cause. No security setting is weakened and no interop behavior is
removed to obtain these results.

## Follow-up: quarantine and fresh component scans

Earlier Nexus runtime file **12**, version **2026.11.05.1**, was quarantined and is
now archived after replacement by file 15. Its notice
lists executable file types, scanner detections and nested archives as possible
reasons; it does not identify the precise failing check. The verified ZIP contains
no nested archives. The current active runtime is file 15, described above; no
source download has been restored on the Nexus Files page.

All three detected members were directly rescanned on **7 November 2026**:

| Member | Completed result | Detecting engine and label |
| --- | --- | --- |
| [Modified winhttp.dll](https://www.virustotal.com/gui/file/0a7b1228b8122633aca507b2b7ead809ebf30bc9d7cc527479d389794eed24e6/detection) | 1/71 | Cynet: `Malicious (score: 100)` |
| [Official Il2CppInterop.Common.dll](https://www.virustotal.com/gui/file/070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f/detection) | 1/70 | VBA32: `TScope.Trojan.MSIL` |
| [Official Capstone 5.0.6 DLL](https://www.virustotal.com/gui/file/651096794b3c3c2a1df24345e22844a0311fca56a4f74ea1cfa29107983760e1/detection) | 1/70 | Cynet: `Malicious (score: 100)` |

These are completed reports with populated results from the detecting engines.
They confirm the detections persist; they do not confirm that the files are malicious
or falsely detected. The outer ZIP's latest report is **0/41**, analysed 5 November
at 10:19:36 Europe/Madrid, with **VBA32 and many other engines timing out**. That
outer result does not establish that its earlier detection was corrected or that its
members passed every scanner.

The native DLL is our modified loader, so its detection must be investigated
separately from the unchanged upstream libraries. The earlier inability to obtain a
completed native report is resolved by this follow-up; it is not a clean native scan.

The [official BepInEx build page](https://builds.bepinex.dev/projects/bepinex_be)
now offers **793**, published after the initial audit. Its Common DLL is still
exactly 41,472 bytes with SHA-256
`070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f`.
Updating the loader to 793 therefore does not change that detection input. Its new
stack-trace logging and macOS ARM support are not an announced antivirus correction.

The packaging change fixed the nested-archive incompatibility; it did not change
the executable bytes or resolve their detections. No source-level defect has been
established as the cause of either vendor's rule. Nexus requires a moderator review
to release a quarantined upload; detecting vendors control their own verdicts.
A [review request draft](publication/nexus-review-request.md) supplies the exact
file reports, source revisions and build steps. It is a draft, not a submitted request.

## Exact samples

| Sample | SHA-256 | Observed result |
| --- | --- | --- |
| Official BepInEx 6.0.0-be.791 IL2CPP x64 ZIP | `bb1c510909b69522733791f3a0817a487379a52da6468a492f1c9c19b3ec6f9a` | 1/65, VBA32 `TScope.Trojan.MSIL`, 4 November |
| New Nexus runtime 2026.11.05.1 | `0ad6f585f5ebb2d044a3d5f873218a9fb4b4ff24d1a1168ef60a61c2ef76e964` | 1/63, VBA32 `TScope.Trojan.MSIL`, 5 November |
| `Il2CppInterop.Common.dll` | `070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f` | 1/71, VBA32 `TScope.Trojan.MSIL`, 28 October |
| Our `BepInEx.MetadataBootstrap.dll` | `e01a533eca74ab3c654bdc7d138cc80dcf63ce0d24988cde9f2ee9875bd47b68` | Completed 0/71 direct report, 5 November |

Reports: [official BepInEx](https://www.virustotal.com/gui/file/bb1c510909b69522733791f3a0817a487379a52da6468a492f1c9c19b3ec6f9a/detection),
[Nexus runtime](https://www.virustotal.com/gui/file/0ad6f585f5ebb2d044a3d5f873218a9fb4b4ff24d1a1168ef60a61c2ef76e964/detection),
[Common DLL](https://www.virustotal.com/gui/file/070e04f2276a8963a6d2a7eb52d43b644f3ae9aa3816c34541124d3862f1b37f/detection),
[bootstrap DLL](https://www.virustotal.com/gui/file/e01a533eca74ab3c654bdc7d138cc80dcf63ce0d24988cde9f2ee9875bd47b68/detection).
These are observations of reports with different dates and engine coverage, not a
simultaneous benchmark. Archive scans do not guarantee inspection of every member.
Nexus's own scan is separate from the completed VirusTotal submission above.

## What was established for the earlier packages

The earlier 41,472-byte Common DLL is byte-for-byte identical in the official
BepInEx ZIP, the published GitHub runtime, and Nexus runtime 2026.11.05.1. All 224
existing BepInEx core/CoreCLR files match the official distribution. That layout-only
repack preserved all 252 executable files from the audited GitHub build; the later
source-build profile above replaces three of them.

This establishes that the directly detected Common bytes are upstream bytes. It
does not establish that Common explains every archive verdict, that our other
components cannot receive detections, or that the vendor's verdict is erroneous.
The earlier published native `winhttp.dll` did not have a completed direct report during the
initial review; its empty results panel was not a clean scan. The follow-up above
confirms Cynet detected that earlier native build, separately from VBA32.

## Source review

The exact Common source is pinned to
[`dbda1cb353b0f4253345dc45136d170b9e50a5a0`](https://github.com/BepInEx/Il2CppInterop/tree/dbda1cb353b0f4253345dc45136d170b9e50a5a0/Il2CppInterop.Common).
All 24 C# files and the project/build settings were reviewed. Its cross-reference
scanners read native code and local lookup databases; some helpers invoke the
game's local metadata initializer through a function pointer. It enumerates its
own process's modules. These are legitimate interop mechanisms and possible
heuristic inputs, not a proven explanation of VBA32's private detection rule.

No Common source calls networking, shell commands, child-process creation,
remote-process memory operations, registry persistence or antivirus configuration.
No custom packer, obfuscator or module initializer was identified. These findings
are limited to that source project and do not certify all dependencies.

The added compatibility layer uses in-process API lookup hooks and a local Python
helper. Review found no added credential collection, exfiltration, autorun
persistence, remote-process injection or antivirus exclusions. Stock BepInEx can
download Unity base libraries during legitimate initialization.

## Fixes and limits

The Nexus layout removes nested ZIPs by expanding Python's standard library and
adjusting its isolated search path. This fixes a concrete packaging incompatibility
with [Nexus's scan requirements](https://help.nexusmods.com/article/117-why-has-my-mod-been-quarantined).
It does not change the detected Common DLL or prove the VBA32 flag was corrected.

Nine archive-boundary tests passed. A fresh extraction passed isolated Python and
dependency imports, five bootstrap checks, and cold symbol-free discovery plus
metadata normalization for two preserved game-input fixtures. Both produced their
expected outputs without modifying the original inputs. No game process was
started, and no antivirus settings were changed.

No source-line cause can be inferred from a generic family label. Changing our
resolver cannot remove a direct verdict on an unchanged upstream DLL. A confirmed
erroneous verdict needs review by the detecting vendor; see
[VirusTotal's guidance](https://docs.virustotal.com/docs/false-positive).
An upstream update is another possible route only if it has an independent
maintenance purpose and passes compatibility testing. Do not strip required interop
behavior or make cosmetic binary changes merely to obtain a different verdict.
