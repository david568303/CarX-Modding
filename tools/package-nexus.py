#!/usr/bin/env python3
"""Repack an audited loader build for Nexus; link existing GitHub source assets.

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
from urllib.parse import unquote, urlsplit
import zipfile

BASE_SHA256 = "e5b17ff5e818e21d046f32de8fa86225425a7ddd57c6f8e55a3fb3f26d23c04e"
DEFAULT_SOURCE_URL = "https://github.com/david568303/CarX-Modding/releases/download/v2026.10.28.1/CarX-Modding-Source-2026.10.28.1.zip"
DEFAULT_SOURCE_SHA256 = "8b1d49f2d756ef90cd791bc536b87d9209cf8c5519ef9babc270b42e7639bae0"
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


def source_download_name(url: str) -> str:
    require(not any(ord(c) < 32 for c in url), "Source URL contains control characters")
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and parsed.netloc == "github.com"
            and not parsed.query and not parsed.fragment,
            "Project source URL must be an HTTPS GitHub release asset URL")
    parts = parsed.path.split("/")
    require(len(parts) == 7 and parts[3:5] == ["releases", "download"]
            and all(parts[i] for i in (1, 2, 5, 6)),
            "Project source URL must identify an explicit GitHub release asset")
    name = safe_name(unquote(parts[-1]))
    require("/" not in name and name.endswith(".zip"), "Project source asset must be a ZIP file")
    return name


def verify_sources(base: dict[str, bytes], manifest: dict, source_path: Path,
                   source_sha: str, source_url: str) -> list[dict]:
    """Verify existing source downloads; never create a source release or use a moving branch."""
    source_name = source_download_name(source_url)
    require(re.fullmatch(r"[0-9a-fA-F]{64}", source_sha) is not None,
            "Project source SHA-256 must have 64 hex digits")
    source_data = source_path.read_bytes()
    require(digest(source_data) == source_sha.lower(), "Existing project source asset SHA-256 mismatch")
    sources = read_archive(source_data, "existing GitHub project source asset")
    require("SOURCE-REVISION.json" in sources, "Project source asset has no revision record")
    revision = json.loads(sources["SOURCE-REVISION.json"])
    for key, source_key in (("sourceRevision", "revision"), ("doorstopRevision", "doorstopRevision")):
        recorded = manifest.get(key, {})
        require(recorded.get("commit") and recorded.get("dirty") is False
                and recorded["commit"] == revision.get(source_key),
                f"Existing project source revision does not match compiled input: {key}")
    embedded = read_archive(base[PREFIX + "source.zip"], "compiled input corresponding source")
    code = {name: data for name, data in embedded.items()
            if name.startswith(("src/", "tools/")) or name == "Directory.Build.props"}
    for name in ("src/Doorstop/LICENSE", "src/Doorstop/src/windows/entrypoint.c",
                 "src/MetadataBootstrap/Bootstrap.cs", "src/ApiResolver/prepare_api_map.py",
                 "src/MetadataNormalizer/normalize_metadata.py", "tools/build.ps1",
                 "tools/build-doorstop.ps1", "Directory.Build.props"):
        require(name in code, f"Compiled source snapshot is incomplete: {name}")
    for name, value in code.items():
        require(name in sources and value.replace(b"\r\n", b"\n") == sources[name].replace(b"\r\n", b"\n"),
                f"Existing GitHub source differs from compiled input: {name}")
    require(sources.get("LICENSE") == base.get("LICENSE"), "Project source root license differs from runtime")
    notices = json.loads(base["licenses/manifest.json"])
    for notice in notices["notices"]:
        name = "licenses/" + notice["file"]
        require(name in sources and digest(sources[name]) == notice["sha256"],
                f"Existing project source license mismatch: {name}")
    records = [{"component": "CarX-Modding and modified UnityDoorstop", "file": source_name,
                "url": source_url, "sha256": source_sha.lower(),
                "commit": revision["revision"], "doorstopCommit": revision["doorstopRevision"],
                "compiledSourceFilesVerified": len(code)}]
    for source in notices["correspondingSources"]:
        archive_name = PREFIX + "sources/" + source["file"]
        require(archive_name in base and digest(base[archive_name]) == source["sha256"],
                f"Upstream source hash mismatch: {archive_name}")
        require(re.fullmatch(r"[0-9a-f]{40}", source["commit"]) is not None
                and source["url"] == f"https://codeload.github.com/{source['component']}/zip/{source['commit']}",
                f"Upstream source URL is not pinned to its exact commit: {source['component']}")
        upstream = read_archive(base[archive_name], archive_name)
        require(all(name.startswith(source["archiveRoot"]) for name in upstream),
                f"Unexpected upstream source root: {archive_name}")
        for required in source["requiredFiles"]:
            require(source["archiveRoot"] + required in upstream,
                    f"Incomplete upstream source: {required}")
        records.append({key: source[key] for key in ("component", "file", "url", "sha256", "commit")})
    require({r["component"] for r in records[1:]} == {"BepInEx/BepInEx", "BepInEx/Il2CppInterop"},
            "Pinned BepInEx and Il2CppInterop corresponding source records are required")
    return records


def source_downloads_text(sources: list[dict]) -> str:
    lines = ["EXISTING CORRESPONDING SOURCE DOWNLOADS", "",
             "No source upload is needed on Nexus. Use these existing GitHub downloads.", ""]
    for source in sources:
        lines.extend((source["component"], "  " + source["file"], "  " + source["url"],
                      "  SHA-256: " + source["sha256"], "  Commit: " + source["commit"]))
        if "doorstopCommit" in source:
            lines.append("  Doorstop commit: " + source["doorstopCommit"])
        lines.append("")
    return "\n".join(lines)


def compliance_text(sources: list[dict]) -> str:
    return f"""CORRESPONDING SOURCE AND REPLACEMENT INSTRUCTIONS

This Nexus download is an installable runtime build. Corresponding source
remains on GitHub; there is no separate source file to install from Nexus.
The existing project release asset contains the complete modified Doorstop
source, managed bootstrap, Python helpers and their build/install tools.
The two additional downloads provide exact unmodified BepInEx and
Il2CppInterop source snapshots. Download each into a separate source folder.

{source_downloads_text(sources)}

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

BUILDING REPLACEMENTS

The project source includes tools/build.ps1 and tools/package.ps1. Use the
existing Visual Studio C++ x64 tools, PowerShell 7 and .NET SDK; these scripts
do not install a compiler. They provision checksum-pinned dependencies.
BepInEx's solution is BepInEx.sln; its Unity IL2CPP project is under
Runtimes/Unity/BepInEx.Unity.IL2CPP. Il2CppInterop's solution is
Il2CppInterop.sln. Keep each upstream snapshot's build files, reference
assemblies and notices, restore its declared dependencies, and follow its
README/build configuration. Interface-compatible replacements need not have
identical file hashes to the original binaries.

The Nexus layout expands the embedded python314.zip into
BepInEx/compatibility/python/Lib, omits its two macOS maintenance fetch scripts,
and sets python314._pth to Lib, ., Lib/site-packages, ..\\tools and
..\\..\\core\\scripts (one entry per line). No compiled executable is changed.
"""


def runtime_notices(original: bytes, sources: list[dict]) -> bytes:
    text = original.decode("utf-8-sig")
    start = text.find("Every loader ZIP contains")
    end = text.find("Replaceable shared DLLs are used.", start)
    require(start >= 0 and end > start, "Source instructions block was not found in third-party notices")
    replacement = ("This Nexus runtime build links existing corresponding source downloads on GitHub.\n"
                   f"The complete modified project source is {sources[0]['file']}:\n"
                   f"{sources[0]['url']}\nIts SHA-256 is {sources[0]['sha256']}.\n"
                   "Exact unmodified BepInEx and Il2CppInterop source archive URLs, commits and\n"
                   "hashes are recorded in SOURCE-DOWNLOADS.txt and licenses/SOURCE-COMPLIANCE.txt.\n"
                   "This runtime contains no source archive; use the existing GitHub downloads.\n\n")
    return (text[:start] + replacement + text[end:]).encode("utf-8")


def build(args: argparse.Namespace) -> dict:
    require(re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(?:\.[0-9]+)?", args.version) is not None,
            "Version must be YYYY.MM.DD or YYYY.MM.DD.N")
    datetime.strptime(".".join(args.version.split(".")[:3]), "%Y.%m.%d")
    require(re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_sha256) is not None, "Expected SHA-256 must have 64 hex digits")
    data = args.runtime_zip.read_bytes()
    base_sha = digest(data)
    require(base_sha == args.expected_sha256.lower(), "Input build SHA-256 does not match the explicitly trusted build")
    base = read_archive(data, str(args.runtime_zip))
    manifest = verify_input(base)
    sources = verify_sources(base, manifest, args.source_zip, args.source_sha256, args.source_url)
    output = args.output_dir.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())),
            "Output directory must be new or empty; refusing stale release artifacts")
    output.mkdir(parents=True, exist_ok=True)
    stem = "CarX-Drift-Racing-Online-2-BepInEx-"
    runtime_name = stem + "Runtime-" + args.version + ".zip"
    runtime_path = output / runtime_name
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
        "Corresponding source remains at existing GitHub release/commit downloads.\n"
        "Exact filenames, URLs and SHA-256 hashes are in SOURCE-DOWNLOADS.txt.\n"
        "No separate source download is needed from Nexus.\n\n"
        "Preserve LICENSE, THIRD-PARTY-NOTICES.md, licenses/, and equivalent source\n"
        "access when redistributing. See licenses/SOURCE-COMPLIANCE.txt.\n\n"
        "Logs: BepInEx/LogOutput.log and BepInEx/metadata-bootstrap.log.\n"
        "Supported metadata schemas: 38/39. Install BepInEx 6 IL2CPP plugins in\n"
        "BepInEx/plugins. This package has no custom car mods or game binaries.\n").encode("utf-8")
    runtime["licenses/SOURCE-COMPLIANCE.txt"] = compliance_text(sources).encode("utf-8")
    runtime["THIRD-PARTY-NOTICES.md"] = runtime_notices(base["THIRD-PARTY-NOTICES.md"], sources)
    runtime["SOURCE-DOWNLOADS.txt"] = source_downloads_text(sources).encode("utf-8")
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
        "correspondingSources": sources,
        "pythonStandardLibrary": {"archiveSha256": digest(base[PYTHON + "python314.zip"]),
                                  "omittedMaintenanceScripts": sorted(maintenance), "files": sorted(stdlib_records, key=lambda r: r["path"])},
        "initialApiMapIncluded": False, "testPluginsIncluded": False, "files": file_records(runtime)})
    runtime_sha = write_archive(runtime_path, runtime, args.version, ("BepInEx/plugins/", "BepInEx/patchers/"))
    for item in json.loads(base["licenses/manifest.json"])["notices"]:
        require(digest(runtime["licenses/" + item["file"]]) == item["sha256"], "A dependency license changed")
    report = {"format": 1, "version": args.version, "inputPackageSha256": base_sha,
              "executableFilesUnchanged": len(binaries), "flattenedStandardLibraryFiles": len(stdlib_records),
              "noNestedArchives": True, "runtimeFiles": len(runtime), "correspondingSources": sources,
              "artifacts": [{"file": runtime_name, "bytes": runtime_path.stat().st_size, "sha256": runtime_sha, "kind": "runtime"}]}
    (output / "nexus-package-verification.json").write_bytes(json_bytes(report))
    (output / "SHA256SUMS.txt").write_text("".join(f"{r['sha256']}  {r['file']}\n" for r in report["artifacts"]), encoding="ascii")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-zip", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=BASE_SHA256)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path, required=True,
                        help="Local copy of the existing complete GitHub source release asset; verified, never republished")
    parser.add_argument("--source-sha256", default=DEFAULT_SOURCE_SHA256)
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args), indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Nexus packaging failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
