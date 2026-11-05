#!/usr/bin/env python3
"""Repack an audited loader build for Nexus; keep corresponding source separate.

No game or upstream program is executed. Only Python's standard library is used.
All existing executable bytes are preserved. The embedded standard-library ZIP
is expanded into Lib and its search path is adjusted for ordinary file imports.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

BASE_SHA256 = "e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e"
DEFAULT_SOURCE_URL = "https://www.nexusmods.com/carxdriftracingonline2/mods/11?tab=files"
PREFIX = "BepInEx/compatibility/"
PYTHON = PREFIX + "python/"
MANIFEST = PREFIX + "package-manifest.json"
ARCHIVES = {".zip", ".whl", ".nupkg", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
BINARIES = {".dll", ".exe", ".pyd"}
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
MAX_UNCOMPRESSED = 1024 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def safe_name(name: str) -> str:
    require(bool(name) and "\\" not in name and ":" not in name
            and not any(ord(c) < 32 or c in '<>"|?*' for c in name),
            f"Unsafe ZIP path: {name!r}")
    require(not name.startswith("/") and not name.endswith("/"), f"Not a ZIP file path: {name!r}")
    parts = name.split("/")
    require(all(p and p not in (".", "..") and p.rstrip(" .") == p for p in parts),
            f"Unsafe ZIP path segments: {name!r}")
    require(all(p.split(".", 1)[0].upper() not in RESERVED for p in parts), f"Reserved Windows path: {name!r}")
    return name


def validate_tree(files: dict[str, bytes], label: str) -> None:
    seen: dict[str, str] = {}
    for name in files:
        safe_name(name)
        folded = name.casefold()
        require(folded not in seen, f"Case-insensitive path collision in {label}: {name}")
        seen[folded] = name
    for name in files:
        for parent in PurePosixPath(name).parents:
            if str(parent) != ".":
                require(str(parent).casefold() not in seen, f"File/directory collision in {label}: {name}")


def read_archive(data: bytes, label: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(sum(i.file_size for i in archive.infolist()) <= MAX_UNCOMPRESSED,
                f"Archive exceeds size limit: {label}")
        for info in archive.infolist():
            require(not (info.flag_bits & 1), f"Encrypted ZIP member in {label}: {info.filename}")
            require(not stat.S_ISLNK(info.external_attr >> 16), f"ZIP link in {label}: {info.filename}")
            if info.is_dir():
                safe_name(info.filename.rstrip("/"))
                continue
            name = safe_name(info.filename)
            require(name not in files, f"Duplicate ZIP entry in {label}: {name}")
            files[name] = archive.read(info)  # Also verifies the entry CRC.
    validate_tree(files, label)
    return files


def put(files: dict[str, bytes], name: str, data: bytes) -> None:
    safe_name(name)
    require(name not in files or files[name] == data, f"Conflicting source file: {name}")
    files[name] = data


def no_archives(files: dict[str, bytes], label: str) -> None:
    for name, data in files.items():
        require(PurePosixPath(name).suffix.lower() not in ARCHIVES,
                f"Nested archive in {label}: {name}")
        require(not zipfile.is_zipfile(io.BytesIO(data)), f"Embedded ZIP file in {label}: {name}")


def file_records(files: dict[str, bytes]) -> list[dict[str, object]]:
    return [{"path": name, "length": len(files[name]), "sha256": digest(files[name])} for name in sorted(files)]


def write_archive(path: Path, files: dict[str, bytes], version: str, empty: tuple[str, ...] = ()) -> str:
    validate_tree(files, str(path))
    no_archives(files, str(path))
    date = tuple(map(int, version.split(".")[:3])) + (0, 0, 0)
    temporary = path.with_suffix(path.suffix + ".partial")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in empty:
            entry = zipfile.ZipInfo(name, date_time=date)
            entry.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(entry, b"")
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=date)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(path)
    actual = read_archive(path.read_bytes(), str(path))
    require(actual == files, f"Output ZIP verification failed: {path}")
    sha = digest(path.read_bytes())
    path.with_name(path.name + ".sha256").write_text(f"{sha}  {path.name}\n", encoding="ascii")
    return sha


def verify_input(files: dict[str, bytes]) -> dict:
    require(MANIFEST in files, "Input build has no package manifest")
    manifest = json.loads(files[MANIFEST])
    paths = set()
    for entry in manifest["files"]:
        name = safe_name(entry["path"])
        require(name not in paths, f"Duplicate manifest entry: {name}")
        paths.add(name)
        require(name in files and len(files[name]) == entry["length"] and digest(files[name]) == entry["sha256"],
                f"Input package manifest mismatch: {name}")
    require(set(files) == paths | {MANIFEST}, "Input build contains unmanifested files")
    for name in ("winhttp.dll", "doorstop_config.ini", "BepInEx/core/BepInEx.MetadataBootstrap.dll",
                 "BepInEx/core/BepInEx.Unity.IL2CPP.dll", "dotnet/coreclr.dll", PYTHON + "python.exe",
                 PYTHON + "python314.zip", PREFIX + "source.zip", "licenses/manifest.json"):
        require(name in files, f"Missing input runtime component: {name}")
    notices = json.loads(files["licenses/manifest.json"])
    for notice in notices["notices"]:
        name = "licenses/" + notice["file"]
        require(name in files and digest(files[name]) == notice["sha256"], f"Input license mismatch: {name}")
    return manifest


def make_sources(base: dict[str, bytes], base_manifest: dict, repo: Path, version: str,
                 base_sha: str, runtime_name: str, source_name: str) -> dict[str, bytes]:
    sources = read_archive(base[PREFIX + "source.zip"], "project corresponding source")
    notices = json.loads(base["licenses/manifest.json"])
    for source in notices["correspondingSources"]:
        archive_name = PREFIX + "sources/" + source["file"]
        require(archive_name in base and digest(base[archive_name]) == source["sha256"],
                f"Upstream source hash mismatch: {archive_name}")
        upstream = read_archive(base[archive_name], archive_name)
        prefix = source["archiveRoot"]
        destination = "upstream/" + source["component"].split("/")[-1] + "/"
        for name, data in upstream.items():
            require(name.startswith(prefix), f"Unexpected upstream source root: {name}")
            put(sources, destination + name[len(prefix):], data)
        for required in source["requiredFiles"]:
            require(destination + required in sources, f"Incomplete expanded upstream source: {required}")
    # The exact compiled-code source above stays authoritative. Add the current
    # maintainer packaging tools needed to reproduce this distribution layout.
    for path in sorted((repo / "tools").glob("*")):
        if path.is_file() and path.suffix in (".ps1", ".py"):
            name = "tools/" + path.name
            if name in sources:
                require(sources[name].replace(b"\r\n", b"\n") == path.read_bytes().replace(b"\r\n", b"\n"),
                        f"Maintainer build tool changed since the compiled input: {name}")
            else:
                put(sources, name, path.read_bytes())
    require("tools/package-nexus.py" in sources, "Nexus packager missing from corresponding source")
    instructions = f"""CORRESPONDING SOURCE: CARX DRIFT RACING ONLINE 2 LOADER {version}

This download is separate from the installable runtime build {runtime_name}.
It contains the exact project/native source embedded in the audited input
build, the complete expanded BepInEx and Il2CppInterop source snapshots,
license/replacement instructions, and the maintainer packaging tools.
There are no nested archives. Upstream reference DLLs are build inputs
included by those upstream repositories, not CarX game binaries.

Original audited input ZIP SHA-256: {base_sha}
Project/native revisions are recorded in SOURCE-REVISION.json.

Build with existing Visual Studio C++ x64 tools, PowerShell 7 and .NET SDK:
  .\\tools\\build.ps1
  .\\tools\\package.ps1

These scripts provision hash-pinned BepInEx/Python dependencies; they do not
install a compiler. Then compute the SHA-256 of your newly built full ZIP:
  Get-FileHash .\\release\\BepInEx-Doorstop-NoPDB.zip -Algorithm SHA256

Reproduce the Nexus layout with Python 3.11 or newer:
  python .\\tools\\package-nexus.py --runtime-zip .\\release\\BepInEx-Doorstop-NoPDB.zip --expected-sha256 YOUR_REBUILT_ZIP_SHA256 --version {version} --output-dir .\\release\\nexus

The packager changes archive layout and Python search paths only. It does
not recompile or change any DLL/EXE/PYD bytes. Replaceable LGPL DLLs remain
under winhttp.dll and BepInEx/core; see licenses/SOURCE-COMPLIANCE.txt.

Source companion filename: {source_name}
"""
    sources["BUILD-NEXUS.txt"] = instructions.encode("utf-8")
    source_notices = sources["THIRD-PARTY-NOTICES.md"].decode("utf-8-sig")
    start = source_notices.find("Every loader ZIP contains")
    end = source_notices.find("Replaceable shared DLLs are used.", start)
    require(start >= 0 and end > start, "Source instructions block missing from source notices")
    sources["THIRD-PARTY-NOTICES.md"] = (source_notices[:start]
        + "This download is the separate complete source companion to the Nexus runtime.\n"
        + "Modified Doorstop and compatibility source/build tools are at this archive root.\n"
        + "The exact unmodified BepInEx and Il2CppInterop source snapshots are expanded\n"
        + "under `upstream/BepInEx/` and `upstream/Il2CppInterop/`. See `BUILD-NEXUS.txt`\n"
        + "and `licenses/SOURCE-COMPLIANCE.txt` for rebuilding and replacing components.\n\n"
        + source_notices[end:]).encode("utf-8")
    sources["SOURCE-REVISION.json"] = json_bytes({
        "format": 1, "version": version, "basePackageSha256": base_sha,
        "project": base_manifest.get("sourceRevision"), "doorstop": base_manifest.get("doorstopRevision"),
        "upstream": notices["correspondingSources"],
        "nexusPackagerSha256": digest(sources["tools/package-nexus.py"]),
        "note": "Compiled-code source is the original build snapshot; Nexus layout tools are included separately."})
    no_archives(sources, "corresponding source")
    return sources


def compliance_text(source_name: str, source_sha: str, source_url: str) -> str:
    return f"""CORRESPONDING SOURCE AND REPLACEMENT INSTRUCTIONS

This Nexus download is an installable runtime build. Complete corresponding
source is provided as a separate download on the same Nexus Files page:
  {source_name}
  {source_url}
  SHA-256: {source_sha}

The source download includes the complete modified UnityDoorstop source,
managed metadata bootstrap and runtime Python helpers, build/install tools,
and the complete unmodified BepInEx and Il2CppInterop source snapshots expanded
under upstream/BepInEx and upstream/Il2CppInterop. See BUILD-NEXUS.txt there.

UnityDoorstop and BepInEx: LGPL-2.1-only. Il2CppInterop: LGPL-3.0-only.
Exact full license texts and third-party notices remain in this runtime ZIP.
Commercial redistribution is permitted subject to those respective terms.
Keep equivalent access to the exact corresponding source beside the runtime
download when redistributing it, including any further modifications.

To install interface-compatible modified replacements, close the game and
replace winhttp.dll or the corresponding DLLs under BepInEx/core. The runtime
Python helper scripts remain directly editable at their installed paths.
This project imposes no signature gate or restriction on reverse engineering
needed to debug modifications to the LGPL components.
"""


def runtime_notices(original: bytes, source_name: str, source_sha: str, source_url: str) -> bytes:
    text = original.decode("utf-8-sig")
    start = text.find("Every loader ZIP contains")
    end = text.find("Replaceable shared DLLs are used.", start)
    require(start >= 0 and end > start, "Source instructions block was not found in third-party notices")
    replacement = (f"This Nexus runtime build keeps corresponding source in a separate download,\n"
                   f"`{source_name}`, available beside the build on the [Nexus Files page]({source_url}).\n"
                   f"Its SHA-256 is `{source_sha}`. It contains complete modified Doorstop and\n"
                   "compatibility source/build instructions plus expanded exact upstream BepInEx\n"
                   "and Il2CppInterop source snapshots. See `licenses/SOURCE-COMPLIANCE.txt`.\n\n")
    return (text[:start] + replacement + text[end:]).encode("utf-8")


def build(args: argparse.Namespace) -> dict:
    require(re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(?:\.[0-9]+)?", args.version) is not None,
            "Version must be YYYY.MM.DD or YYYY.MM.DD.N")
    datetime.strptime(".".join(args.version.split(".")[:3]), "%Y.%m.%d")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256) is not None, "Expected SHA-256 must have 64 hex digits")
    require(args.source_url.startswith("https://") and not any(c in args.source_url for c in "\r\n\x00"),
            "Source URL must be HTTPS and contain no control characters")
    data = args.runtime_zip.read_bytes()
    base_sha = digest(data)
    require(base_sha == args.expected_sha256.lower(), "Input build SHA-256 does not match the explicitly trusted build")
    base = read_archive(data, str(args.runtime_zip))
    manifest = verify_input(base)
    repo = Path(__file__).resolve().parents[1]
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stem = "CarX-Drift-Racing-Online-2-BepInEx-"
    runtime_name = stem + "Runtime-" + args.version + ".zip"
    source_name = stem + "Sources-" + args.version + ".zip"
    runtime_path, source_path = output / runtime_name, output / source_name
    require(not runtime_path.exists() and not source_path.exists(), "Output ZIP already exists; use a fresh output directory")
    sources = make_sources(base, manifest, repo, args.version, base_sha, runtime_name, source_name)
    # The source bundle's replacement instructions refer to its own expanded
    # layout, avoiding an impossible self-referential archive checksum.
    sources["licenses/SOURCE-COMPLIANCE.txt"] = ("CORRESPONDING SOURCE AND REPLACEMENTS\n\n"
        "This is the complete separate source companion for the Nexus runtime.\n"
        "Project and Doorstop source/build tools are at this archive root.\n"
        "BepInEx and Il2CppInterop snapshots are expanded under upstream/.\n"
        "Read BUILD-NEXUS.txt, each component LICENSE, and THIRD-PARTY-NOTICES.md.\n"
        "You may rebuild and replace interface-compatible LGPL DLLs; this project\n"
        "does not prohibit reverse engineering needed to debug those changes.\n").encode("utf-8")
    sources["SOURCE-FILES.json"] = json_bytes({"format": 1, "files": file_records(sources)})
    source_sha = write_archive(source_path, sources, args.version)
    runtime = {name: value for name, value in base.items()
               if name != PREFIX + "source.zip" and not name.startswith(PREFIX + "sources/")
               and name != PYTHON + "python314.zip"
               and not name.startswith(PYTHON + "Lib/site-packages/capstone/include/")
               and name not in {PREFIX + "tools/requirements.txt", "BepInEx/core/scripts/requirements.txt", MANIFEST}}
    stdlib = read_archive(base[PYTHON + "python314.zip"], "official Python standard library")
    # These are macOS maintenance fetch scripts, not interpreter runtime code.
    maintenance = {"ctypes/macholib/fetch_macholib", "ctypes/macholib/fetch_macholib.bat"}
    stdlib_records = []
    for name, value in stdlib.items():
        if name in maintenance:
            continue
        target = PYTHON + "Lib/" + name
        put(runtime, target, value)
        stdlib_records.append({"path": target, "originalPath": name, "sha256": digest(value)})
    runtime[PYTHON + "python314._pth"] = b"Lib\n.\nLib/site-packages\n..\\tools\n..\\..\\core\\scripts\n"
    runtime["README.txt"] = (f"CARX DRIFT RACING ONLINE 2 - BEPINEX RUNTIME {args.version}\n\n"
        "Close the game. Extract this ZIP beside CarX Drift Racing Online 2.exe,\n"
        "then launch normally through Steam. No compiler or separate launcher is\n"
        "needed. First launch can take several minutes to generate interop files.\n\n"
        "This is the installable Windows x64 BepInEx 6 IL2CPP compatibility build.\n"
        "It contains compiled loader DLLs and required runtime Python scripts,\n"
        "not a development project. Standard-library bytecode is installed as\n"
        "ordinary files under BepInEx/compatibility/python/Lib; no nested archives\n"
        "or source snapshots are inside the runtime download.\n\n"
        f"Complete corresponding source is a separate download: {source_name}\n"
        f"Source download page: {args.source_url}\nSource SHA-256: {source_sha}\n\n"
        "Preserve LICENSE, THIRD-PARTY-NOTICES.md, licenses/, and equivalent source\n"
        "access when redistributing. See licenses/SOURCE-COMPLIANCE.txt.\n\n"
        "Logs: BepInEx/LogOutput.log and BepInEx/metadata-bootstrap.log.\n"
        "Supported metadata schemas: 38/39. Install BepInEx 6 IL2CPP plugins in\n"
        "BepInEx/plugins. This package has no custom car mods or game binaries.\n").encode("utf-8")
    runtime["licenses/SOURCE-COMPLIANCE.txt"] = compliance_text(source_name, source_sha, args.source_url).encode("utf-8")
    runtime["THIRD-PARTY-NOTICES.md"] = runtime_notices(base["THIRD-PARTY-NOTICES.md"], source_name, source_sha, args.source_url)
    runtime["SOURCE-DOWNLOADS.txt"] = (f"Corresponding source: {source_name}\n"
        f"Download page: {args.source_url}\nSHA-256: {source_sha}\n"
        "Complete source/build instructions and expanded exact upstream source\n"
        "snapshots are in that separate file. Retain equivalent source access.\n").encode("utf-8")
    validate_tree(runtime, "Nexus runtime")
    no_archives(runtime, "Nexus runtime")
    forbidden = {".c", ".h", ".cpp", ".cs", ".sln", ".csproj", ".ps1", ".bat", ".lua", ".pdb", ".log"}
    for name in runtime:
        require(not name.startswith(("src/", "tools/", "tests/", "assets/", ".work/", ".git/")),
                f"Development/private tree in runtime: {name}")
        require(PurePosixPath(name).suffix.lower() not in forbidden, f"Development file in runtime: {name}")
        require("__pycache__" not in PurePosixPath(name).parts, f"Unexpected generated cache: {name}")
        if name.endswith(".pyc"):
            require(any(r["path"] == name for r in stdlib_records), f"Unverified bytecode in runtime: {name}")
    binaries = {name: digest(value) for name, value in base.items() if PurePosixPath(name).suffix.lower() in BINARIES}
    require(all(name in runtime and digest(runtime[name]) == sha for name, sha in binaries.items()),
            "An input DLL, EXE or PYD was changed or removed")
    runtime[MANIFEST] = json_bytes({
        "format": 1, "profile": "nexus-runtime", "version": args.version,
        "createdUtc": datetime.now(timezone.utc).isoformat(), "inputPackageSha256": base_sha,
        "sourceRevision": manifest.get("sourceRevision"), "doorstopRevision": manifest.get("doorstopRevision"),
        "sourceCompanion": {"filename": source_name, "sha256": source_sha, "url": args.source_url},
        "pythonStandardLibrary": {"archiveSha256": digest(base[PYTHON + "python314.zip"]),
                                  "omittedMaintenanceScripts": sorted(maintenance), "files": sorted(stdlib_records, key=lambda r: r["path"])},
        "initialApiMapIncluded": False, "testPluginsIncluded": False, "files": file_records(runtime)})
    runtime_sha = write_archive(runtime_path, runtime, args.version, ("BepInEx/plugins/", "BepInEx/patchers/"))
    for item in json.loads(base["licenses/manifest.json"])["notices"]:
        require(digest(runtime["licenses/" + item["file"]]) == item["sha256"], "A dependency license changed")
    report = {"format": 1, "version": args.version, "inputPackageSha256": base_sha,
              "executableFilesUnchanged": len(binaries), "flattenedStandardLibraryFiles": len(stdlib_records),
              "noNestedArchives": True, "runtimeFiles": len(runtime), "sourceFiles": len(sources),
              "artifacts": [{"file": runtime_name, "bytes": runtime_path.stat().st_size, "sha256": runtime_sha, "kind": "runtime"},
                            {"file": source_name, "bytes": source_path.stat().st_size, "sha256": source_sha, "kind": "corresponding-source"}]}
    (output / "nexus-package-verification.json").write_bytes(json_bytes(report))
    (output / "SHA256SUMS.txt").write_text("".join(f"{r['sha256']}  {r['file']}\n" for r in report["artifacts"]), encoding="ascii")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-zip", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=BASE_SHA256)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Nexus packaging failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
