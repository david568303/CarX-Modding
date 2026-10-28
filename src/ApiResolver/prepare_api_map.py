"""Build a validated IL2CPP alias map directly from paired native binaries.

No symbol files, reference builds, downloaded schemas, or saved mappings are
consulted. The native binder is discovered from PE unwind/import/export data;
canonical SDK declarations and native semantic checks establish API identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import pefile

from discover_api_bindings import discover_bindings
from canonical_api_schema import canonicalize_bindings

ROOT = Path.cwd()
REQUIRED_APIS = {"il2cpp_init", "il2cpp_runtime_invoke", "il2cpp_method_get_name"}
DISCOVERY_METHOD = "binary-loader-schema-and-native-semantics"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_map(result: dict, exports: dict[str, int]) -> None:
    mapping = result["mapping"]
    missing = REQUIRED_APIS - set(mapping)
    if missing:
        raise ValueError(f"Required APIs are missing: {', '.join(sorted(missing))}")
    if result.get("rejected") or result.get("unmapped") or result["mapping_count"] != result["canonical_slot_count"]:
        raise ValueError("API recovery was incomplete; no runtime map will be written")
    if len(mapping) != result["mapping_count"] or len(set(mapping.values())) != len(mapping):
        raise ValueError("Invalid or ambiguous API mapping count")
    witnesses = {item["canonical"]: item for item in result["witnesses"]}
    if len(witnesses) != len(result["witnesses"]) or set(witnesses) != set(mapping):
        raise ValueError("Every API must have one unique native binding witness")
    for canonical, alias in mapping.items():
        if not re.fullmatch(r"il2cpp_[A-Za-z0-9_]+", canonical):
            raise ValueError(f"Invalid canonical API name: {canonical!r}")
        if not re.fullmatch(r"[A-Za-z0-9_]+", alias) or alias not in exports:
            raise ValueError(f"Invalid or absent export for {canonical}")
        witness = witnesses[canonical]
        if witness["actual"] != alias or int(witness["export_rva"], 16) != exports[alias]:
            raise ValueError(f"Missing or inconsistent loader witness for {canonical}")


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, newline="\n", dir=path.parent,
                                         prefix=".map-", suffix=".partial", delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(unity_path: Path, game_path: Path) -> tuple[dict, str]:
    before = (digest(unity_path), digest(game_path))
    discovery = discover_bindings(unity_path, game_path)
    canonical = canonicalize_bindings(unity_path, game_path, discovery)
    semantic = canonical.get("semantic_validation", {})
    if not semantic.get("passed") or not semantic.get("checks"):
        raise ValueError("Native API semantic validation did not establish a complete match")
    result = dict(discovery)
    result.update(canonical)
    result.update(format=2, method=DISCOVERY_METHOD, uses_symbols=False, pdb_used=False,
                  canonical_slot_count=discovery["binding_count"],
                  mapping_count=len(canonical["mapping"]), rejected=[], unmapped=[])
    with pefile.PE(str(game_path), fast_load=True) as game:
        game.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        exports = {symbol.name.decode("ascii"): symbol.address
                   for symbol in game.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name}
        validate_map(result, exports)
        target = {"timestamp": game.FILE_HEADER.TimeDateStamp,
                  "size_of_image": game.OPTIONAL_HEADER.SizeOfImage}
        directory = game.OPTIONAL_HEADER.DATA_DIRECTORY[0]
        for alias in result["mapping"].values():
            rva = exports[alias]
            section = game.get_section_by_rva(rva)
            if (directory.VirtualAddress <= rva < directory.VirtualAddress + directory.Size
                    or section is None or not section.Characteristics & 0x20000000):
                raise ValueError(f"API export is not executable local code: {alias}")
    if before != (digest(unity_path), digest(game_path)):
        raise ValueError("Game binaries changed while API discovery was running")
    result.update(unity_player_sha256=before[0], game_assembly_sha256=before[1], target=target)
    ini = ("; Generated offline from native binder dataflow, SDK declarations, and native semantics.\n"
           "; Regenerated automatically when target inputs change.\n"
           "[Target]\nFormat=2\nDiscovery=binary-loader-schema\n"
           f"TimeDateStamp={target['timestamp']:x}\nSizeOfImage={target['size_of_image']:x}\n\n[Exports]\n"
           + "".join(f"{name}={alias},{exports[alias]:x}\n" for name, alias in sorted(result["mapping"].items())))
    return result, ini


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unity", type=Path, default=ROOT / "UnityPlayer.dll")
    parser.add_argument("--game", type=Path, default=ROOT / "GameAssembly.dll")
    parser.add_argument("--output", type=Path, default=ROOT / "doorstop_api.ini")
    parser.add_argument("--json", type=Path, default=ROOT / "BepInEx/cache/compatibility/api-map.json")
    args = parser.parse_args()
    try:
        protected = {args.unity.resolve(), args.game.resolve()}
        if args.output.resolve() in protected or args.json.resolve() in protected or args.output.resolve() == args.json.resolve():
            raise ValueError("Map outputs must be separate from the game binaries and each other")
        result, ini = prepare(args.unity, args.game)
        atomic_write(args.json, json.dumps(result, indent=2) + "\n")
        atomic_write(args.output, ini, "ascii")
        print(f"Verified {result['mapping_count']} API bindings directly from native binaries; no symbol files used.")
        print(args.output.resolve())
        print(args.json.resolve())
        return 0
    except (OSError, ValueError, KeyError, pefile.PEFormatError) as error:
        print(f"API map preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
