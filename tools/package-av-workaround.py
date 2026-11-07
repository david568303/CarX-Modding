#!/usr/bin/env python3
"""Package four verified source builds over one immutable audited runtime.

The ordinary Nexus packager remains unchanged. This profile only accepts the
four tested DLL hashes, pinned public source revisions, and committed notices.
It produces one installable runtime ZIP; no source archive is published on Nexus.
"""
from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import urlsplit

_spec = importlib.util.spec_from_file_location("nexus_archive_io", Path(__file__).with_name("package-nexus.py"))
zipio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(zipio)
require, digest, json_bytes = zipio.require, zipio.digest, zipio.json_bytes
BASE_SHA256 = "fb5be7816afe5489699c65ef19a92806e2cf2a06a0cf603716ff04c17414aa63"
BASE_INVENTORY_SHA256 = "cd85645dd5ceda190e45e3643757cd78ce317bf9b60f31b0ab4337cc1fac8810"
ROOT_REPO = "david568303/CarX-Modding"
NATIVE_REPO = "david568303/UnityDoorstop"
NATIVE_COMMIT = "7316db427ac7cbc5962cbfa5046de7a342345ee6"
COMMON_COMMIT = "dbda1cb353b0f4253345dc45136d170b9e50a5a0"
BEPINEX_COMMIT = "b782da4ac54e1072d2857f4a2f77c80c3ef08005"
BASE_SOURCE_COMMIT = "bd21c6483e89d38ff5faa77e256c1046510004a9"
CAPSTONE_PROFILE = {
    "finalTestedProfile": True,
    "nativeVersion": "5.0.9", "pythonBindingVersion": "5.0.6",
    "commit": "022575848782a4801fd150fdbc927effcbca0864",
    "archiveSha256": "eafc74835ab22d9745b29d4535c1723d6e0ddb79df840cf2f41125de9a441233",
    "dllSha256": "af3a1ae919c7ba700c42e5f133ffa022dfa3f05fa79672865c790243e769e727",
    "patchPath": "patches/capstone/5.0.9-initialize-encoding-size.patch",
    "patchSha256": "7a286bb090bf07bf113f42b0abfc273eeed96a20e50b3a48ea2ec48179e90907",
    "extraFiles": [
        {"path": "patches/capstone/5.0.9-version.rc", "sha256": "14103cdb3967c5836dd0a9581a41122746afa71fea589e35a3637e8ccf5c7b74"},
        {"path": "patches/capstone/5.0.9-msvc-provenance.cmake", "sha256": "3c4fa7ee9e07d3ecc97c6f07d24a15c520633f53f273d2c8ca644069554b0dd9"},
    ],
    "description": "5.0.9 maintenance/security fixes, encoding-size initialization fix, MSVC stack protection and CFG; full architecture/detail/allocator features retained",
}
DOBBY_PROFILE = {
    "finalTestedProfile": True,
    "version": "1.0.5",
    "commit": "888d971214900374edbca6206fad6ded8a2c1311",
    "archiveSha256": "00c0a582fc69efd52aa3a95449d27882384b653eb0e6524b79e796e8a8ef807d",
    "dllSha256": "fac2aa3399e8b73352181bfaa5fb9e3f55eb4ebf638d35c04a0857e5bc764001",
    "helperPath": "tools/build-dobby.ps1",
    "helperSha256": "fffe9f2e88ffd90c3d030470f3e5a9f3d0153a8e5bf0b590212606e7720c9fb1",
    "extraFiles": [
        {"path": "patches/dobby/1.0.5-version.rc", "sha256": "fd681551c72c1cbb19c4d09b3f3d6e193ab2c3fa1061ca1d212415edc893cb33"},
        {"path": "patches/dobby/1.0.5-msvc-provenance.cmake", "sha256": "c2f7e62f87d4210c9fe55e01c442cf79bed66f6074b7cc30ff7da77b8f813c60"},
    ],
    "description": "Unchanged official Windows x64 Release feature profile and two-phase Prepare/Commit API; truthful version resources, static MSVC release CRT, stack protection, CFG, ASLR and DEP",
}
MANIFEST = zipio.MANIFEST
SITE = zipio.PYTHON + "Lib/site-packages/"
CAPSTONE_DLL = SITE + "capstone/lib/capstone.dll"
DOBBY_DLL = "BepInEx/core/dobby.dll"
RECORD = SITE + "capstone-5.0.6.dist-info/RECORD"
REPLACEMENTS = {
    "winhttp.dll": "722170e9d492f75f16ada1068eabdcdc06ed2fbe90154d2ceca5832562ef1588",
    "BepInEx/core/Il2CppInterop.Common.dll": "1928f201590f2e2b6827adba98191d253e5074769e93405a20f254e4efa984e6",
    CAPSTONE_DLL: CAPSTONE_PROFILE["dllSha256"],
    DOBBY_DLL: DOBBY_PROFILE["dllSha256"],
}
NOTICE_PROFILE = {
    "licenses/MSVC-2026-CRT-NOTICE.txt": {
        "sha256": "69c87d0458a2a04d016a6190e93f1784d7e5c14c2168e7a130390dbefc0b50ce",
        "sourceUrl": "https://visualstudio.microsoft.com/license-terms/",
    },
    "licenses/MSVC-2026-Runtime-LICENSE.txt": {
        "sha256": "c719078e78b378064328cc3a5bad39e347491e64beedf9c1cac9a7d49ea55aa1",
        "sourceUrl": "https://visualstudio.microsoft.com/wp-content/uploads/2025/10/Visual-C-V14-License-Redistributable_and_Runtime_ENU.docx",
    },
    "licenses/MSVC-2026-Community-LICENSE.txt": {
        "sha256": "a6bcf1feb139a29d3ec21aafa6125f30f5c838e6ee07d2d141373d9cce1cb675",
        "sourceUrl": "https://visualstudio.microsoft.com/wp-content/uploads/2025/10/Visual_Studio_2026-License-Community_ENU.docx",
    },
    "licenses/Dobby-LLVM-exception-NOTICE.txt": {
        "sha256": "21bfefe67d8c6f27e75ddbb85ef544146efe5f50c05fe1a945fe897816218b81",
        "sourceUrl": "https://raw.githubusercontent.com/llvm/llvm-project/1fdec59bffc11ae37eb51a1b9869f0696bfd5312/llvm/LICENSE.TXT",
    },
    "licenses/Dobby-MSVC-2026-CRT-NOTICE.txt": {
        "sha256": "13797a774980c419e548bc15b80353b1a53cf6482d0b503722b390208c57434f",
        "sourceUrl": "https://visualstudio.microsoft.com/license-terms/",
    },
}
NOTICE_NAMES = set(NOTICE_PROFILE)
HELPERS = ("tools/build-doorstop.ps1", "tools/build-il2cpp-common.ps1", "tools/build-capstone.ps1", DOBBY_PROFILE["helperPath"])
TEXT_CHANGES = {"README.txt", "SOURCE-DOWNLOADS.txt", "THIRD-PARTY-NOTICES.md", "licenses/SOURCE-COMPLIANCE.txt", MANIFEST, RECORD}
BASE_RECONSTRUCTION = {
    "packagerUrl": "https://github.com/david568303/CarX-Modding/blob/ffe30889b80f3e871982e07a25ba1882720cd313/tools/package-nexus.py",
    "runtimeUrl": "https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/BepInEx-Doorstop-NoPDB.zip",
    "runtimeSha256": "e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e",
    "sourceUrl": "https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/CarX-Modding-Source-2026.10.28.1.zip",
    "sourceSha256": "8b1d49f2d756ef90cd791bc536b87d9209cf8c5519ef9babc270b42e7639bae0",
    "version": "2026.11.05.2",
    "instructions": "Run the pinned ordinary Nexus packager with --runtime-zip, --expected-sha256, --source-zip, --source-sha256, --source-url, --version 2026.11.05.2 and a fresh --output-dir. Its one Runtime ZIP is the reconstructed base.",
}


def canonical_base_inventory(files: dict[str, bytes], manifest: dict) -> str:
    """Pin every extracted byte and all provenance, excluding only creation time.

    Canonical JSON represents the manifest's structure; only createdUtc is removed.
    ZIP compression, entry order and container timestamps are outside this inventory.
    """
    created = manifest.get("createdUtc")
    require(isinstance(created, str) and len(created) < 64, "Base creation time must be a UTC timestamp")
    timestamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
    require(timestamp.tzinfo is not None and timestamp.utcoffset().total_seconds() == 0,
            "Base creation time must be a UTC timestamp")
    stable_manifest = {key: value for key, value in manifest.items() if key != "createdUtc"}
    stable_bytes = json.dumps(stable_manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    normalized = dict(files)
    normalized[MANIFEST] = stable_bytes
    return digest(json_bytes(zipio.file_records(normalized)))


def verify_manifest(files: dict[str, bytes]) -> dict:
    zipio.validate_tree(files, "audited base")
    zipio.no_archives(files, "audited base")
    require(MANIFEST in files, "Audited base has no package manifest")
    manifest = json.loads(files[MANIFEST])
    require(manifest.get("profile") == "nexus-runtime" and manifest.get("version") == "2026.11.05.2",
            "Unexpected audited base profile/version")
    paths: set[str] = set()
    for entry in manifest["files"]:
        name = zipio.safe_name(entry["path"])
        require(name not in paths, f"Duplicate manifest entry: {name}")
        paths.add(name)
        require(name in files and len(files[name]) == entry["length"] and digest(files[name]) == entry["sha256"],
                f"Base package manifest mismatch: {name}")
    require(set(files) == paths | {MANIFEST}, "Base contains unmanifested or missing files")
    for name in (*REPLACEMENTS, RECORD, "README.txt", "SOURCE-DOWNLOADS.txt", "THIRD-PARTY-NOTICES.md",
                 "licenses/manifest.json", "licenses/SOURCE-COMPLIANCE.txt", "LICENSE"):
        require(name in files, f"Base is missing required input: {name}")
    for notice in json.loads(files["licenses/manifest.json"])["notices"]:
        name = "licenses/" + notice["file"]
        require(name in files and digest(files[name]) == notice["sha256"], f"Base license mismatch: {name}")
    require(sum(PurePosixPath(n).suffix.lower() in zipio.BINARIES for n in files) == 252,
            "Audited base must contain exactly 252 executable files")
    return manifest


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    require(process.returncode == 0, "Git verification failed: " + " ".join(args) + "\n" + process.stderr.strip())
    return process.stdout.strip()


def archive_source(component: str, repository: str, commit: str, sha256: str | None = None) -> dict:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "Source commit must be a full immutable Git SHA")
    record = {"component": component, "repository": repository, "commit": commit,
              "url": f"https://codeload.github.com/{repository}/zip/{commit}"}
    if sha256:
        record["archiveSha256"] = sha256
    return record


def maintained_capstone_files() -> list[dict]:
    records = list(CAPSTONE_PROFILE.get("extraFiles", []))
    if CAPSTONE_PROFILE.get("patchPath"):
        records.append({"path": CAPSTONE_PROFILE["patchPath"], "sha256": CAPSTONE_PROFILE["patchSha256"]})
    paths: set[str] = set()
    for record in records:
        name = zipio.safe_name(record["path"])
        require(name.startswith("patches/capstone/") and name not in paths
                and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is not None,
                "Invalid maintained Capstone source/resource record")
        paths.add(name)
    return records


def maintained_dobby_files() -> list[dict]:
    records = list(DOBBY_PROFILE["extraFiles"])
    paths: set[str] = set()
    for record in records:
        name = zipio.safe_name(record["path"])
        require(name.startswith("patches/dobby/") and name not in paths
                and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is not None,
                "Invalid maintained Dobby source/resource record")
        paths.add(name)
    return records


def require_tested_profiles() -> None:
    require(CAPSTONE_PROFILE.get("finalTestedProfile") is True, "The final tested Capstone source-build profile has not been pinned")
    require(DOBBY_PROFILE.get("finalTestedProfile") is True, "The final tested Dobby source-build profile has not been approved")


def make_sources(root_commit: str) -> dict:
    records = [
        archive_source("Maintained compatibility code, build helpers and patches", ROOT_REPO, root_commit),
        archive_source("Complete modified UnityDoorstop source", NATIVE_REPO, NATIVE_COMMIT),
        archive_source("Il2CppInterop 1.5.3 source (Common rebuilt)", "BepInEx/Il2CppInterop", COMMON_COMMIT,
                       "96d223a475c885ef08118a3adaee0c2ed5d65edd83fbea9987e5a305f1123ac5"),
        archive_source("Capstone native " + CAPSTONE_PROFILE["nativeVersion"] + " upstream source", "capstone-engine/capstone",
                       CAPSTONE_PROFILE["commit"], CAPSTONE_PROFILE["archiveSha256"]),
        archive_source("Dobby " + DOBBY_PROFILE["version"] + " upstream source (Windows native rebuilt)", "BepInEx/Dobby",
                       DOBBY_PROFILE["commit"], DOBBY_PROFILE["archiveSha256"]),
        archive_source("Unchanged BepInEx be.791 source", "BepInEx/BepInEx", BEPINEX_COMMIT,
                       "53f87ca8e5ab9891ab3e22af0dc021a17b5bdc3f0fa917f815d6d0667d90b259"),
    ]
    maintained = {r["path"]: r for r in maintained_capstone_files() + maintained_dobby_files()}
    maintained[DOBBY_PROFILE["helperPath"]] = {"path": DOBBY_PROFILE["helperPath"], "sha256": DOBBY_PROFILE["helperSha256"]}
    paths = sorted(set(HELPERS) | set(maintained))
    helpers = [{"path": path, "url": f"https://github.com/{ROOT_REPO}/blob/{root_commit}/{path}",
                **({"sha256": maintained[path]["sha256"]} if path in maintained else {})} for path in paths]
    return {"rootCommit": root_commit, "nativeCommit": NATIVE_COMMIT, "records": records, "helpers": helpers,
            "capstoneSourceBuild": dict(CAPSTONE_PROFILE), "dobbySourceBuild": dict(DOBBY_PROFILE)}


def collect_sources(repo: Path) -> dict:
    require_tested_profiles()
    require(Path(git(repo, "rev-parse", "--show-toplevel")).resolve() == repo.resolve(), "Unexpected repository root")
    require(not git(repo, "status", "--porcelain=v1", "--untracked-files=all"), "Root repository must be clean and committed")
    root_commit = git(repo, "rev-parse", "HEAD")
    native = repo / "src/Doorstop"
    require(not git(native, "status", "--porcelain=v1", "--untracked-files=all"), "Native submodule must be clean and committed")
    require(git(native, "rev-parse", "HEAD") == NATIVE_COMMIT, "Native source does not match the tested source-build commit")
    require(git(repo, "ls-tree", "HEAD", "src/Doorstop").split()[:3] == ["160000", "commit", NATIVE_COMMIT],
            "Root commit must pin the tested native submodule")
    git(repo, "diff", "--exit-code", BASE_SOURCE_COMMIT, root_commit, "--", "src/MetadataBootstrap", "src/ApiResolver", "src/MetadataNormalizer", "Directory.Build.props")
    for helper in make_sources(root_commit)["helpers"]:
        path = helper["path"]
        git(repo, "cat-file", "-e", f"HEAD:{path}")
        require((repo / path).is_file(), f"Missing committed build helper: {path}")
        if helper.get("sha256"):
            require(digest((repo / path).read_bytes()) == helper["sha256"], f"Maintained build source/resource changed: {path}")
    for path in ("licenses/source-build-notices.json", *sorted(NOTICE_NAMES)):
        git(repo, "cat-file", "-e", f"HEAD:{path}")
    git(native, "cat-file", "-e", "HEAD:build-msvc.ps1")
    for path, repository, commit in ((repo, ROOT_REPO, root_commit), (native, NATIVE_REPO, NATIVE_COMMIT)):
        remote = git(path, "remote", "get-url", "origin")
        require(remote in (f"https://github.com/{repository}.git", f"https://github.com/{repository}", f"git@github.com:{repository}.git"),
                "Source origin is not the expected public GitHub repository")
        refs = git(path, "ls-remote", f"https://github.com/{repository}.git")
        require(any(line.split()[0] == commit for line in refs.splitlines()), "Source commit must be pushed before packaging")
    return make_sources(root_commit)


def load_notices(repo: Path) -> tuple[dict[str, bytes], list[dict]]:
    spec = json.loads((repo / "licenses/source-build-notices.json").read_text(encoding="utf-8-sig"))
    require(spec.get("format") == 1 and isinstance(spec.get("files"), list), "Invalid source-build notice specification")
    records = spec["files"]
    validate_notice_records(records)
    files: dict[str, bytes] = {}
    for record in records:
        path = zipio.safe_name(record["path"])
        data = (repo / path).read_bytes()
        require(bool(data) and digest(data) == NOTICE_PROFILE[path]["sha256"], f"Source-build notice checksum mismatch: {path}")
        files[path] = data
    return files, records


def validate_notice_records(records: list[dict]) -> None:
    require(len(records) == len(NOTICE_NAMES) and {r["path"] for r in records} == NOTICE_NAMES,
            "Exactly the five approved source-build notice paths are required")
    for record in records:
        path = zipio.safe_name(record["path"])
        expected = NOTICE_PROFILE[path]
        url = urlsplit(record["sourceUrl"])
        require(url.scheme == "https" and not url.username and not url.password
                and record["sourceUrl"] == expected["sourceUrl"],
                f"Notice URL must match its approved official source: {path}")
        require(record["sha256"] == expected["sha256"], f"Source-build notice checksum mismatch: {path}")
        require(isinstance(record["component"], str) and bool(record["component"].strip()), "Notice component is missing")


def wheel_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def update_record(original: bytes, old_dll: bytes, new_dll: bytes) -> bytes:
    rows = list(csv.reader(io.StringIO(original.decode("utf-8"))))
    seen: set[str] = set()
    found = 0
    for row in rows:
        require(len(row) == 3 and row[0] not in seen, "Invalid or duplicate wheel RECORD row")
        seen.add(row[0])
        zipio.safe_name(row[0])
        if row[0] == "capstone/lib/capstone.dll":
            require(row[1:] == [wheel_hash(old_dll), str(len(old_dll))], "Base wheel RECORD does not match its DLL")
            row[1:] = [wheel_hash(new_dll), str(len(new_dll))]
            found += 1
    require(found == 1, "Wheel RECORD must contain exactly one Capstone DLL row")
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue().encode("utf-8")


def source_text(sources: dict) -> str:
    lines = ["CORRESPONDING SOURCE — EXACT PUBLIC GITHUB REVISIONS", "",
             "Download all six source snapshots. The root archive does not expand its native submodule;",
             "the separate complete UnityDoorstop snapshot below is required for the rebuilt native DLL.", ""]
    for record in sources["records"]:
        lines.extend((record["component"], "  " + record["url"], "  Commit: " + record["commit"]))
        if record.get("archiveSha256"):
            lines.append("  Source archive SHA-256: " + record["archiveSha256"])
        lines.append("")
    lines.append("Maintained build helpers, resources and any required Capstone patch:")
    for helper in sources["helpers"]:
        lines.append("  " + helper["url"])
        if helper.get("sha256"):
            lines.append("  File SHA-256: " + helper["sha256"])
    if CAPSTONE_PROFILE.get("patchPath"):
        lines.append("  Capstone patch SHA-256: " + CAPSTONE_PROFILE["patchSha256"])
    lines.extend(("", "Capstone native version: " + CAPSTONE_PROFILE["nativeVersion"],
                  "Unchanged Python binding version: " + CAPSTONE_PROFILE["pythonBindingVersion"],
                  "Capstone source-build profile: " + CAPSTONE_PROFILE["description"], "",
                  "Dobby native version: " + DOBBY_PROFILE["version"],
                  "Dobby source-build profile: " + DOBBY_PROFILE["description"],
                  "Dobby runtime source is unchanged; its official two-phase API and feature profile are retained.",
                  "Dobby uses the static release CRT; no separate Microsoft runtime DLL or installer is added.", "",
                  "Source remains on GitHub; only the installable runtime is uploaded to Nexus.", ""))
    return "\n".join(lines)


def compliance_text(sources: dict) -> str:
    return ("CORRESPONDING SOURCE AND REPLACEMENT INSTRUCTIONS\n\n"
            + source_text(sources)
            + "\nReconstruct the source tree by extracting the maintained root snapshot, then placing\n"
            "the complete modified native snapshot at src/Doorstop. Keep each upstream snapshot\n"
            "and its license/build/reference files. No game binaries or generated game metadata\n"
            "are needed to build these shared libraries. Use installed Visual Studio x64 C++\n"
            "tools, CMake and a .NET SDK; these helpers install no compiler.\n\n"
            "Native: run tools/build-doorstop.ps1 -Release (delegates to the pinned native\n"
            "build-msvc.ps1 with normal CRT startup). Common: run tools/build-il2cpp-common.ps1\n"
            "-SourceZip <exact Il2CppInterop source ZIP> -BuildRoot <fresh directory>. It uses\n"
            "the unchanged upstream Release/netstandard2.0 project, embedded symbols and a\n"
            "documented SDK-selection roll-forward to an installed SDK. No external PDB is required.\n"
            "Capstone: run tools/build-capstone.ps1 -SourceArchive <exact upstream ZIP>\n"
            "-BuildRoot <fresh directory>; use the exact native source version and any patch\n"
            "listed above. The unchanged Python bindings retain their recorded package version.\n"
            "Dobby: run tools/build-dobby.ps1 -SourceArchive <exact BepInEx/Dobby source ZIP>\n"
            "-BuildRoot <fresh directory>. Its unchanged official Windows x64 Release feature\n"
            "profile and two-phase Prepare/Commit API are retained, with standard version\n"
            "resources and MSVC protections. Its static CRT needs no new external CRT DLL.\n"
            "Rebuilt files can differ with compiler versions; ABI-compatible replacements need\n"
            "not have the same hash. The packaged hashes are recorded in the package manifest.\n\n"
            "Close the game before replacing winhttp.dll, BepInEx/core/Il2CppInterop.Common.dll,\n"
            "BepInEx/core/dobby.dll or BepInEx/compatibility/python/Lib/site-packages/capstone/lib/capstone.dll.\n"
            "UnityDoorstop/BepInEx retain LGPL-2.1-only and Il2CppInterop LGPL-3.0-only.\n"
            "Capstone retains its BSD/LLVM terms; retained MSVC notices apply to source-built\n"
            "native components. Dobby retains Apache 2.0 and its LLVM clear-cache component's\n"
            "Apache-2.0 WITH LLVM-exception notice. Keep all license texts, notices and equivalent source access.\n"
            "No signature gate or restriction on reverse engineering for LGPL debugging is imposed.\n")


def runtime_notices(original: bytes, sources: dict, notices: list[dict]) -> bytes:
    text = original.decode("utf-8-sig")
    text = text.replace("| Il2CppInterop | 1.5.3+dbda1cb |", "| Il2CppInterop | 1.5.3+dbda1cb; Common source build |", 1)
    text = text.replace("| Capstone native disassembler and Python bindings | 5.0.6 |",
                        "| Capstone native disassembler and Python bindings | Native " + CAPSTONE_PROFILE["nativeVersion"]
                        + " source build; Python bindings " + CAPSTONE_PROFILE["pythonBindingVersion"] + " |", 1)
    text = text.replace("| LLVM-derived portions in Capstone | 5.0.6 |",
                        "| LLVM-derived portions in Capstone | " + CAPSTONE_PROFILE["nativeVersion"] + " |", 1)
    text = text.replace("| Dobby (BepInEx fork) | 1.0.5 / 888d971 |",
                        "| Dobby (BepInEx fork) | 1.0.5 / 888d971; Windows source build |", 1)
    start = text.find("The machine-readable [license manifest]")
    end = text.find("Copyright holders include", start)
    require(start >= 0 and end > start, "Baseline component provenance block is missing")
    text = (text[:start] + "The baseline [license manifest](licenses/manifest.json) retains the original\n"
            "component notices and exact upstream source pins. This profile rebuilds the modified\n"
            "UnityDoorstop loader, Il2CppInterop.Common 1.5.3, Capstone native DLL and Dobby.\n"
            "Common's C# source is unchanged; its helper records SDK selection and deterministic\n"
            "build settings. Capstone's exact native version/profile and any patch are recorded\n"
            "in SOURCE-DOWNLOADS.txt; its Python binding version is unchanged.\n"
            "Dobby's official Windows x64 feature profile and two-phase Prepare/Commit API are\n"
            "unchanged; its source build adds standard version resources and MSVC protections.\n"
            "The other 248 DLL/EXE/PYD files remain byte-identical to the audited baseline.\n"
            "These four DLLs are source builds and are not the original official binary bytes.\n\n"
            "Additional source-build notices (including LLVM attribution and static MSVC CRT):\n"
            + "".join(f"- [{r['path']}]({r['path']}) — {r['component']}\n" for r in notices) + "\n" + text[end:])
    start = text.find("This Nexus runtime build links existing corresponding source downloads on GitHub.")
    end = text.find("Replaceable shared DLLs are used.", start)
    require(start >= 0 and end > start, "Baseline source-download block is missing")
    text = (text[:start] + "Complete corresponding source and build helpers are hosted at immutable public\n"
            f"GitHub revisions: maintained root `{sources['rootCommit']}` and complete modified\n"
            f"native fork `{sources['nativeCommit']}`. The root archive alone does not expand\n"
            "the native submodule. Download the native fork plus the exact Common, Capstone,\n"
            "Dobby and BepInEx snapshots listed in `SOURCE-DOWNLOADS.txt`; follow the retained\n"
            "`licenses/SOURCE-COMPLIANCE.txt`. No source archive is embedded in this runtime.\n\n" + text[end:])
    start = text.find("## Release policy")
    require(start >= 0, "Baseline release-policy block is missing")
    text = (text[:start] + "## Release policy\n\n"
            "Installable ZIPs retain LICENSE, this notice and licenses/. Corresponding source\n"
            "is available through the exact GitHub downloads and instructions recorded above.\n"
            "Only the built runtime is uploaded to Nexus. Preserve the notices, replacement\n"
            "rights and equivalent access to the complete exact source when redistributing.\n")
    return text.encode("utf-8")


def repack(base_data: bytes, replacements: dict[str, bytes], sources: dict,
           extra_notices: dict[str, bytes], notice_records: list[dict], version: str) -> tuple[dict[str, bytes], dict]:
    require_tested_profiles()
    require(re.fullmatch(r"20\d{2}\.\d{2}\.\d{2}(?:\.\d+)?", version) is not None, "Version must be date based")
    datetime.strptime(".".join(version.split(".")[:3]), "%Y.%m.%d")
    base = zipio.read_archive(base_data, "audited runtime ZIP")
    baseline_manifest = verify_manifest(base)
    base_inventory = canonical_base_inventory(base, baseline_manifest)
    require(base_inventory == BASE_INVENTORY_SHA256, "Base payload inventory does not match the immutable audited runtime")
    actual_base_sha256 = digest(base_data)
    require(set(replacements) == set(REPLACEMENTS), "Exactly the four approved replacement paths are required")
    for name, data in replacements.items():
        require(digest(data) == REPLACEMENTS[name], f"Unexpected replacement hash: {name}")
    require(set(extra_notices) == NOTICE_NAMES, "Unexpected or missing source-build notice paths")
    validate_notice_records(notice_records)
    for record in notice_records:
        name = record["path"]
        require(name not in base and bool(extra_notices[name])
                and digest(extra_notices[name]) == NOTICE_PROFILE[name]["sha256"], "Source-build notice overwrite or hash mismatch")
    require(sources == make_sources(sources["rootCommit"]), "Source records must use the exact tested public GitHub revisions")
    runtime = dict(base)
    runtime.update(replacements)
    runtime.update(extra_notices)
    runtime[RECORD] = update_record(base[RECORD], base[CAPSTONE_DLL], replacements[CAPSTONE_DLL])
    runtime["README.txt"] = (f"CARX DRIFT RACING ONLINE 2 — BEPINEX RUNTIME {version}\n\n"
        "Extract this ZIP into the game folder beside the executable and launch through Steam.\n"
        "First launch prepares API bindings, normalized metadata and interop files.\n"
        "Later launches reuse validated caches.\n\n"
        "Rebuilt Dobby with Windows version metadata and security protections to address antivirus detections.\n\n"
        "This Windows x64 runtime includes source-built Doorstop, Common, Capstone and Dobby.\n"
        "Exact sources and build helpers are listed in SOURCE-DOWNLOADS.txt.\n"
        "Retain LICENSE, THIRD-PARTY-NOTICES.md, licenses/ and equivalent source access.\n\n"
        "Install BepInEx 6 IL2CPP plugins in BepInEx/plugins. Supported metadata schemas: 38/39.\n"
        "Logs: BepInEx/LogOutput.log and BepInEx/metadata-bootstrap.log.\n").encode("utf-8")
    runtime["SOURCE-DOWNLOADS.txt"] = source_text(sources).encode("utf-8")
    runtime["licenses/SOURCE-COMPLIANCE.txt"] = compliance_text(sources).encode("utf-8")
    runtime["THIRD-PARTY-NOTICES.md"] = runtime_notices(base["THIRD-PARTY-NOTICES.md"], sources, notice_records)
    changed_binaries = [n for n in base if PurePosixPath(n).suffix.lower() in zipio.BINARIES and runtime[n] != base[n]]
    require(set(changed_binaries) == set(REPLACEMENTS), "Binary changes exceeded the approved set")
    require(all(runtime[n] == data for n, data in base.items() if n not in TEXT_CHANGES | set(REPLACEMENTS)),
            "Unexpected payload change")
    for name, data in base.items():
        if (name.startswith("licenses/") and name != "licenses/SOURCE-COMPLIANCE.txt") or name == "LICENSE":
            require(runtime[name] == data, f"An existing license or notice changed: {name}")
    runtime[MANIFEST] = json_bytes({"format": 1, "profile": "nexus-source-build-runtime", "version": version,
        "createdUtc": datetime.now(timezone.utc).isoformat(), "inputPackageSha256": actual_base_sha256,
        "auditedBaseZipSha256": BASE_SHA256, "basePayloadInventorySha256": base_inventory,
        "baseSourceRevision": baseline_manifest.get("sourceRevision"), "baseDoorstopRevision": baseline_manifest.get("doorstopRevision"),
        "sourceRevision": {"commit": sources["rootCommit"], "dirty": False},
        "doorstopRevision": {"commit": sources["nativeCommit"], "dirty": False},
        "correspondingSources": sources["records"], "buildHelpers": sources["helpers"],
        "capstoneSourceBuild": dict(CAPSTONE_PROFILE), "dobbySourceBuild": dict(DOBBY_PROFILE), "additionalNotices": notice_records,
        "replacements": [{"path": n, "baselineSha256": digest(base[n]), "sha256": REPLACEMENTS[n], "length": len(runtime[n])} for n in sorted(REPLACEMENTS)],
        "unchangedExecutableFiles": 248, "initialApiMapIncluded": False, "testPluginsIncluded": False,
        "files": zipio.file_records({n: data for n, data in runtime.items() if n != MANIFEST})})
    zipio.validate_tree(runtime, "source-build runtime")
    zipio.no_archives(runtime, "source-build runtime")
    require(set(runtime) - set(base) == NOTICE_NAMES, "Unexpected added runtime files")
    report = {"format": 1, "version": version, "baseSha256": actual_base_sha256, "auditedBaseZipSha256": BASE_SHA256,
              "basePayloadInventorySha256": base_inventory, "baseReconstruction": BASE_RECONSTRUCTION,
              "sourceRevision": sources["rootCommit"],
              "nativeRevision": sources["nativeCommit"], "replacedExecutableFiles": 4, "unchangedExecutableFiles": 248,
              "noNestedArchives": True, "runtimeFiles": len(runtime), "sourceArchiveIncluded": False,
              "replacementHashes": dict(REPLACEMENTS), "additionalNotices": notice_records}
    return runtime, report


def package(args: argparse.Namespace, sources: dict, extra_notices: dict[str, bytes], notice_records: list[dict]) -> dict:
    require(not args.output_dir.is_symlink(), "Output directory must be an ordinary directory")
    output = args.output_dir.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "Output directory must be fresh or empty")
    replacements = {"winhttp.dll": args.winhttp.read_bytes(), "BepInEx/core/Il2CppInterop.Common.dll": args.common.read_bytes(),
                    CAPSTONE_DLL: args.capstone.read_bytes(), DOBBY_DLL: args.dobby.read_bytes()}
    files, report = repack(args.base_zip.read_bytes(), replacements, sources, extra_notices, notice_records, args.version)
    output.mkdir(parents=True, exist_ok=True)
    name = f"CarX-Drift-Racing-Online-2-BepInEx-Runtime-{args.version}.zip"
    path = output / name
    sha256 = zipio.write_archive(path, files, args.version, ("BepInEx/plugins/", "BepInEx/patchers/"))
    report["artifact"] = {"file": name, "bytes": path.stat().st_size, "sha256": sha256, "kind": "runtime"}
    (output / "source-build-package-verification.json").write_bytes(json_bytes(report))
    (output / "SHA256SUMS.txt").write_text(f"{sha256}  {name}\n", encoding="ascii")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-zip", type=Path, required=True)
    parser.add_argument("--winhttp", type=Path, required=True)
    parser.add_argument("--common", type=Path, required=True)
    parser.add_argument("--capstone", type=Path, required=True)
    parser.add_argument("--dobby", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", default="2026.11.07.2")
    args = parser.parse_args()
    try:
        repo = Path(__file__).resolve().parents[1]
        sources = collect_sources(repo)
        notices, records = load_notices(repo)
        print(json.dumps(package(args, sources, notices, records), indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Source-build packaging failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
