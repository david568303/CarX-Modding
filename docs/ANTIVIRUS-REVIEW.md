# Antivirus review — updated 7 November 2026

The installable CarX Drift Racing Online 2 package has a suspected false positive,
not a vendor-confirmed false positive. A low detection count does not establish safety.

## Follow-up: quarantine and fresh component scans

Nexus runtime file **12**, version **2026.11.05.1**, is now quarantined. Its notice
lists executable file types, scanner detections and nested archives as possible
reasons; it does not identify the precise failing check. The verified ZIP contains
no nested archives. Only the runtime is active on the Nexus Files page; no source
download has been restored there.

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

## What was established

The 41,472-byte Common DLL is byte-for-byte identical in the official BepInEx ZIP,
the published GitHub runtime, and the new Nexus runtime. All 224 existing BepInEx
core/CoreCLR files match the official distribution. The Nexus repack preserves all
252 executable files from the audited GitHub build.

This establishes that the directly detected Common bytes are upstream bytes. It
does not establish that Common explains every archive verdict, that our other
components cannot receive detections, or that the vendor's verdict is erroneous.
The current native `winhttp.dll` did not have a completed direct report during the
initial review; its empty results panel was not a clean scan. The follow-up above
now confirms Cynet also detects the current native build, separately from VBA32.

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
