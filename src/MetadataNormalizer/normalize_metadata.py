#!/usr/bin/env python3
"""Normalize MFuscator IL2CPP metadata using file structure, not game addresses.

The recognizer infers the rotating header key, header length, shuffled triple
order, section boundaries, variable-width indices, and section XOR family.
Its output is an ordinary IL2CPP metadata file for Cpp2IL/Il2CppInterop.
Only metadata schema versions 38 and 39 are currently supported.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile

sys.dont_write_bytecode = True

MAGIC = 0xFAB11BAF
NAMES = (
    "StringLiterals", "StringLiteralData", "Strings", "Events", "Properties", "Methods",
    "ParameterDefaultValues", "FieldDefaultValues", "FieldAndParameterDefaultValueData",
    "FieldMarshaledSizes", "Parameters", "Fields", "GenericParameters", "GenericParameterConstraints",
    "GenericContainers", "NestedTypes", "Interfaces", "VtableMethods", "InterfaceOffsets",
    "TypeDefinitions", "Images", "Assemblies", "FieldRefs", "ReferencedAssemblies", "AttributeData",
    "AttributeDataRange", "UnresolvedVirtualCallParameterTypes", "UnresolvedVirtualCallParameterRanges",
    "WindowsRuntimeTypeNames", "WindowsRuntimeStrings", "ExportedTypeDefinitions",
)
HEADER_SIZE = 8 + 12 * len(NAMES)
ENCRYPTED = (0, 1, 2, 4, 5, 11, 21)

class DecodeError(ValueError):
    pass

@dataclass(frozen=True)
class Section:
    claimed: int
    size: int
    count: int
    slot: int
    start: int = 0

def sha(data):
    return hashlib.sha256(data).hexdigest()

def u32(data, offset=0):
    return struct.unpack_from("<I", data, offset)[0]

def width(count):
    return 1 if count <= 255 else 2 if count <= 65535 else 4

def xor_cycle(data, key, sign=1):
    # Translation tables move the per-byte work into CPython for large tables.
    tables = [bytes(value ^ ((key + sign * index) & 255) for value in range(256)) for index in range(256)]
    output = bytearray(len(data))
    for index, table in enumerate(tables):
        output[index::256] = data[index::256].translate(table)
    return bytes(output)

def get_unity_version(game: Path):
    player = game.parent / "UnityPlayer.dll"
    if not player.is_file():
        raise DecodeError(f"UnityPlayer.dll is required beside {game.name} to identify the metadata schema")
    text = player.read_bytes().decode("utf-16le", errors="ignore")
    versions = re.findall(r"(?<![0-9])([0-9]{4}|[0-9]{1,2})\.([0-9]+)\.([0-9]+)([abfp])([0-9]+)", text)
    if not versions:
        raise DecodeError("Cannot read a Unity product version from UnityPlayer.dll")
    major, minor, patch, kind, build = versions[0]
    parsed = (int(major), int(minor), int(patch), "abfp".index(kind), int(build))
    if parsed < (6000, 3, 0, 0, 5):
        raise DecodeError("This normalizer requires metadata schema 38 or 39")
    if parsed < (6000, 3, 0, 1, 1):
        version = 38
    elif parsed < (6000, 5, 0, 0, 3):
        version = 39
    else:
        raise DecodeError("This Unity release uses a newer metadata schema; refusing to guess its layout")
    return f"{major}.{minor}.{patch}{kind}{build}", version

def find_headers(data):
    # A v38+ mangled header consists of shuffled offset/size/count triples and
    # decoy triples. The first string-literal offset is zero, revealing four
    # consecutive key-stream bytes. Scan a bounded prefix, never game RVAs.
    candidates = []
    for length in range(12 * len(NAMES), min(16384, len(data) - 4) + 1, 12):
        if not all(data[length + index] == (data[length] + index) & 255 for index in range(4)):
            continue
        encrypted_header = data[:length]
        for key in range(256):
            for sign in (1, -1):
                clear = bytes(value ^ ((key + sign * index) & 255) for index, value in enumerate(encrypted_header))
                words = struct.unpack("<" + "I" * (length // 4), clear)
                for order in itertools.permutations(range(3)):
                    sections = []
                    for position in range(0, len(words), 3):
                        claimed, size, count = [words[position + item] for item in order]
                        if not (length - 128 <= claimed < len(data) and size <= len(data) and count <= size and claimed + size <= len(data) + 128):
                            continue
                        if size == count == 0 or count > 0 and size / count <= 256:
                            sections.append(Section(claimed, size, count, position * 4))
                    if len(sections) >= len(NAMES):
                        candidates.append((len(sections), length, key, sign, order, sections))
    return sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1]))

def find_layouts(data, header_length, candidates):
    results = []
    ordered = sorted(candidates, key=lambda section: (section.claimed, section.slot))
    def walk(index, position, used, sections):
        if len(results) > 256:
            raise DecodeError("Metadata layout is ambiguous: more than 256 candidate layouts")
        if index == len(NAMES):
            results.append(sections)
            return
        alignment = 8 if index == 8 else 4
        canonical_position = position + HEADER_SIZE - header_length
        position += (-canonical_position) % alignment
        for candidate in ordered:
            if candidate.slot in used:
                continue
            delta = position - candidate.claimed
            if not (16 <= abs(delta) <= 64) or position + candidate.size > len(data):
                continue
            # Nonempty early tables and basic public-format strides prune
            # decoy paths before a complete cross-table schema check.
            if index < 26 and (candidate.size == 0 or candidate.count == 0):
                continue
            fixed = {0:4, 4:20, 8:1, 14:16, 15:4, 17:4, 21:68, 23:4, 25:8, 27:8, 30:4}.get(index)
            if fixed and candidate.size != candidate.count * fixed:
                continue
            section = Section(candidate.claimed, candidate.size, candidate.count, candidate.slot, position)
            walk(index + 1, position + candidate.size, used | {candidate.slot}, sections + [section])
    walk(0, header_length, set(), [])
    unique = {}
    for result in results:
        signature = tuple((item.start, item.size, item.count) for item in result)
        unique[signature] = result
    return list(unique.values())

def check_strides(sections, version):
    td = width(sections[19].count)
    gc = width(sections[14].count)
    parameter = width(sections[10].count) if version >= 39 else 4
    candidates = []
    for type_width in (1, 2, 4):
        strides = {
            0:4, 3:20 + type_width, 4:20, 5:20 + td + type_width + parameter + gc,
            6:parameter + type_width + 4, 7:8 + type_width, 8:1, 9:8 + type_width,
            10:8 + type_width, 11:8 + type_width, 12:12 + gc, 13:type_width,
            14:16, 15:4, 16:type_width, 17:4, 18:4 + type_width,
            19:68 + 3 * type_width + gc, 20:32 + 2 * td, 21:68,
            22:type_width + 4, 23:4, 25:8, 26:type_width, 27:8,
            28:4 + type_width, 30:4,
        }
        if all(sections[index].size == sections[index].count * stride for index, stride in strides.items()):
            candidates.append({"type":type_width, "type_definition":td, "generic_container":gc, "parameter":parameter, "strides":strides})
    if len(candidates) != 1:
        raise DecodeError(f"Variable-width schema has {len(candidates)} valid interpretations")
    return candidates[0]

def looks_like_strings(probe):
    return 0 in probe and all(value == 0 or value >= 32 and value != 127 for value in probe)

def decrypt_sections(data, sections, widths):
    literal_key = data[sections[0].start]
    type_width = widths["type"]
    token_offsets = {4:16, 5:4 + widths["type_definition"] + type_width + 4 + widths["parameter"] + widths["generic_container"], 11:4 + type_width}
    def valid(index, probe):
        if index == 0:
            return probe[:4] == b"\0" * 4
        if index == 1:
            return probe[:2] == b"\0\0"
        if index == 2:
            return looks_like_strings(probe)
        if index in token_offsets:
            expected = {4:0x17000001, 5:0x06000001, 11:0x04000001}[index]
            return u32(probe, token_offsets[index]) == expected
        return u32(probe) == 0 and u32(probe, 4) == 0x20000001
    families = []
    for component in ("size", "start"):
        for literal_sign in (1, -1):
            addend = (literal_sign * literal_key - getattr(sections[0], component)) & 255
            keys = {}
            for index in ENCRYPTED:
                section = sections[index]
                probe = data[section.start:section.start + min(section.size, 64)]
                possible = []
                for sign in (1, -1):
                    key = (sign * (getattr(section, component) + addend)) & 255
                    clear = bytes(value ^ ((key + offset) & 255) for offset, value in enumerate(probe))
                    if valid(index, clear):
                        possible.append(key)
                possible = sorted(set(possible))
                if len(possible) != 1:
                    break
                keys[index] = possible[0]
            else:
                families.append((component, addend, keys))
    if not families:
        raise DecodeError("No common rotating section-key family passes all seven independent probes")
    outputs = {}
    for component, addend, keys in families:
        signature = tuple(sorted(keys.items()))
        outputs[signature] = (component, addend, keys)
    if len(outputs) != 1:
        raise DecodeError("Section-key family remains ambiguous")
    component, addend, keys = next(iter(outputs.values()))
    clear = {index:xor_cycle(data[sections[index].start:sections[index].start + sections[index].size], key) for index, key in keys.items()}
    return clear, {"component":component, "addend":addend, "keys":{NAMES[index]:key for index, key in keys.items()}}

def validate_tables(data, sections, decrypted, widths):
    def table(index):
        section = sections[index]
        return decrypted.get(index, data[section.start:section.start + section.size])
    literals = table(0)
    offsets = struct.unpack("<" + "I" * sections[0].count, literals)
    if sections[0].count != sections[1].count + 1 or offsets[0] != 0 or any(a > b for a, b in zip(offsets, offsets[1:])) or offsets[-1] > sections[1].size:
        raise DecodeError("String literal offsets/counts do not agree with literal data")
    types = table(19)
    stride = widths["strides"][19]
    sums = [0] * 8
    for offset in range(0, len(types), stride):
        counts = struct.unpack_from("<8H", types, offset + stride - 24)
        sums = [a + b for a, b in zip(sums, counts)]
    for total, index in zip(sums, (5, 4, 11, 3, 15, 17, 16, 18)):
        if total != sections[index].count:
            raise DecodeError(f"Type-definition member counts disagree with {NAMES[index]}: {total} != {sections[index].count}")
    images = table(20)
    type_sum = export_sum = attribute_sum = 0
    td = widths["type_definition"]
    stride = widths["strides"][20]
    for offset in range(0, len(images), stride):
        type_sum += u32(images, offset + 8 + td)
        export_sum += u32(images, offset + 12 + 2 * td)
        attribute_sum += u32(images, offset + 28 + 2 * td)
    if type_sum != sections[19].count or sections[20].count != sections[21].count or export_sum != sections[30].count or attribute_sum + 1 != sections[25].count:
        raise DecodeError("Image type/export/assembly/custom-attribute totals do not match their tables")
    ranges = table(25)
    starts = [u32(ranges, offset + 4) for offset in range(0, len(ranges), 8)]
    if not starts or starts[0] != 0 or any(a > b for a, b in zip(starts, starts[1:])) or not starts[-1] <= sections[24].size <= starts[-1] + 3:
        raise DecodeError("Custom-attribute ranges do not tile attribute data")
    next_index = 0
    calls = table(27)
    for offset in range(0, len(calls), 8):
        start, length = struct.unpack_from("<ii", calls, offset)
        if start != next_index or length < 0:
            raise DecodeError("Unresolved virtual-call ranges are discontinuous")
        next_index += length
    if next_index != sections[26].count:
        raise DecodeError("Unresolved virtual-call ranges do not cover parameter types")
    strings = table(2)
    for index, name_offset, record_stride in ((19, 0, widths["strides"][19]), (20, 0, widths["strides"][20]), (5, 0, widths["strides"][5]), (11, 0, widths["strides"][11])):
        section = table(index)
        for position in range(0, len(section), record_stride):
            string_offset = u32(section, position + name_offset)
            if string_offset >= len(strings) or strings.find(b"\0", string_offset) < 0:
                raise DecodeError(f"{NAMES[index]} contains an invalid string index")
    return {"type_definitions":sections[19].count, "methods":sections[5].count, "fields":sections[11].count, "images":sections[20].count, "assemblies":sections[21].count, "string_literals":sections[1].count, "checks":["all schema strides", "all literal offsets", "all type member totals", "image table totals", "attribute range coverage", "virtual-call range coverage", "all type/image/method/field name indices"]}

def validate_native(sections, decrypted, header_length, key, sign, order, native, native_sections):
    if header_length != native["header"]["length"] or key != native["header"]["key"] or sign != 1:
        raise DecodeError("Reconstructed header disagrees with the game's independently inferred native decoder")
    matched = set()
    for native_section in native_sections:
        matches = [(index, section) for index, section in enumerate(sections) if section.start == native_section["file_offset"] and section.size == native_section["byte_size"]]
        if len(matches) != 1:
            raise DecodeError("A native-decoded metadata range has no unique canonical section")
        index, section = matches[0]
        if section.slot + order[0] * 4 != native_section["offset_field"] or section.slot + order[1] * 4 != native_section["size_field"]:
            raise DecodeError("Native and structural interpretations disagree on header field placement")
        if index not in decrypted or sha(decrypted[index]) != native_section["decoded_sha256"]:
            raise DecodeError(f"{NAMES[index]} disagrees byte-for-byte with native decoder semantics")
        matched.add(index)
    if matched != set(ENCRYPTED):
        raise DecodeError("Native and structural decoders disagree on which metadata tables are encrypted")

def normalize(data, version, native=None, native_sections=None):
    errors = []
    successful = {}
    headers = find_headers(data)
    if not headers:
        raise DecodeError("No rotating XOR header with a complete triple table was recognized")
    for score, header_length, key, sign, order, candidates in headers:
        if native and (header_length != native["header"]["length"] or key != native["header"]["key"] or sign != 1):
            continue
        for sections in find_layouts(data, header_length, candidates):
            try:
                widths = check_strides(sections, version)
                decrypted, family = decrypt_sections(data, sections, widths)
                if native:
                    validate_native(sections, decrypted, header_length, key, sign, order, native, native_sections)
                validation = validate_tables(data, sections, decrypted, widths)
                result_size = max(HEADER_SIZE, max(section.start + section.size for section in sections) + HEADER_SIZE - header_length)
                result = bytearray(result_size)
                struct.pack_into("<II", result, 0, MAGIC, version)
                for index, section in enumerate(sections):
                    start = section.start + HEADER_SIZE - header_length
                    struct.pack_into("<III", result, 8 + index * 12, start, section.size, section.count)
                    result[start:start + section.size] = decrypted.get(index, data[section.start:section.start + section.size])
                evidence = {"schema_version":1, "metadata_version":version, "header_length":header_length, "header_xor_key":key, "header_xor_direction":sign, "triple_order":{"offset":order[0], "size":order[1], "count":order[2]}, "index_widths":{k:v for k,v in widths.items() if k != "strides"}, "section_xor":family, "validation":validation, "sections":[{"name":NAMES[index], "source_start":section.start, "source_claimed_offset":section.claimed, "source_offset_delta":section.start-section.claimed, "source_header_slot":section.slot, "size":section.size, "count":section.count} for index,section in enumerate(sections)]}
                successful[sha(result)] = (bytes(result), evidence)
            except DecodeError as error:
                errors.append(str(error))
    if len(successful) != 1:
        raise DecodeError(f"Expected one validated metadata reconstruction, found {len(successful)}. Last rejections: {errors[-5:]}")
    return next(iter(successful.values()))

def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

def validate_standard(data, version):
    if len(data) < HEADER_SIZE or u32(data) != MAGIC or u32(data, 4) != version:
        raise DecodeError("Standard metadata header does not match the engine's schema")
    sections = [Section(start, size, count, index * 12, start) for index in range(len(NAMES)) for start, size, count in [struct.unpack_from("<III", data, 8 + index * 12)]]
    if any((section.size and (section.start < HEADER_SIZE or section.start + section.size > len(data))) or (not section.size and section.count) for section in sections):
        raise DecodeError("Standard metadata section lies outside the file or has an invalid count")
    widths = check_strides(sections, version)
    return validate_tables(data, sections, {}, widths)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="GameAssembly.dll; read only")
    parser.add_argument("--metadata", type=Path, required=True, help="Original metadata; read only")
    parser.add_argument("--api-map", type=Path, help="Verified Doorstop API map; defaults to doorstop_api.ini beside GameAssembly.dll")
    parser.add_argument("--output", type=Path, required=True, help="Separate normalized metadata output")
    args = parser.parse_args()
    try:
        api_map = args.api_map or args.game.parent / "doorstop_api.ini"
        if args.output.resolve() in (args.game.resolve(), args.metadata.resolve(), api_map.resolve(), (args.game.parent / "UnityPlayer.dll").resolve()):
            raise DecodeError("Output must be separate from game and original metadata")
        unity, version = get_unity_version(args.game)
        original = args.metadata.read_bytes()
        if len(original) >= 8 and u32(original) == MAGIC:
            validation = validate_standard(original, version)
            normalized, evidence = original, {"schema_version":1, "metadata_version":version, "method":"already-standard-validated", "validation":validation}
        else:
            try:
                from infer_native_decoder import infer_decoder, decode_eager_sections
            except ImportError as error:
                raise DecodeError("Native validation requires companion infer_native_decoder.py and Python packages pefile and capstone") from error
            native = infer_decoder(args.game, api_map)
            native_sections = decode_eager_sections(original, native)
            normalized, evidence = normalize(original, version, native, native_sections)
            evidence["native_validation"] = dict(native, sections=[{key:value for key,value in section.items() if key != "data"} for section in native_sections])
        evidence.update({"unity_version":unity, "input_sha256":sha(original), "output_sha256":sha(normalized), "game_sha256":sha(args.game.read_bytes()), "input_size":len(original), "output_size":len(normalized)})
        atomic_write(args.output, normalized)
        atomic_write(Path(str(args.output) + ".evidence.json"), (json.dumps(evidence, indent=2) + "\n").encode())
        print(json.dumps({"output":str(args.output.resolve()), "metadata_version":version, "sha256":sha(normalized), "validation":evidence["validation"]}))
        return 0
    except (OSError, ValueError, struct.error) as error:
        print(f"Metadata normalization failed: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
