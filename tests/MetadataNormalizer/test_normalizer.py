"""Regression tests using private local fixtures; no game files are distributed.

Run python -B -m unittest discover -s tests/MetadataNormalizer -v.
Set CARX_NORMALIZED_FIXTURE to test another already-normalized v39 file.
"""
from __future__ import annotations
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "MetadataNormalizer" / "normalize_metadata.py"
spec = importlib.util.spec_from_file_location("metadata_normalizer_under_test", SOURCE)
normalizer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = normalizer
spec.loader.exec_module(normalizer)


def mangle(clear, seed, order, offset_keys=False, header_sign=1):
    """Independent fixture encoder: shuffle header records and change all keys.

    Metadata payloads and schema counts come from the parser-validated clear
    fixture. This models update changes without editing the native game DLL.
    """
    rng = random.Random(seed)
    sections = [struct.unpack_from("<III", clear, 8 + index * 12) for index in range(len(normalizer.NAMES))]
    decoy_count = rng.randrange(5, 28)
    header_length = 12 * (len(sections) + decoy_count)
    shift = header_length - normalizer.HEADER_SIZE
    output = bytearray(len(clear) + shift + 256)
    output[header_length:len(clear) + shift] = clear[normalizer.HEADER_SIZE:]
    addend = rng.randrange(256)
    triples = []
    for index, (start, size, count) in enumerate(sections):
        actual_start = start + shift
        delta = rng.choice((-1, 1)) * rng.randrange(4, 17) * 4
        triple = [0, 0, 0]
        triple[order[0]], triple[order[1]], triple[order[2]] = actual_start - delta, size, count
        triples.append(triple)
        if index in normalizer.ENCRYPTED:
            component = actual_start if offset_keys else size
            key = (rng.choice((-1, 1)) * (component + addend)) & 255
            payload = clear[start:start + size]
            # The encoder uses direct position-specific XOR. Production uses
            # block translation tables, so this also checks that optimization.
            output[actual_start:actual_start + size] = bytes(value ^ ((key + position) & 255) for position, value in enumerate(payload))
    for _ in range(decoy_count):
        triples.append([rng.randrange(len(output) + 1, 0x7FFFFFFF) for _ in range(3)])
    rng.shuffle(triples)
    header_key = rng.randrange(256)
    header = b"".join(struct.pack("<3I", *triple) for triple in triples)
    output[:header_length] = bytes(value ^ ((header_key + header_sign * position) & 255) for position, value in enumerate(header))
    return bytes(output), {"header_length":header_length, "header_key":header_key, "order":order, "addend":addend}


class NormalizerRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(os.environ.get("CARX_NORMALIZED_FIXTURE", ROOT / ".work" / "metadata-research" / "current.native-validated.dat"))
        if not fixture.is_file():
            raise unittest.SkipTest("Provide CARX_NORMALIZED_FIXTURE or run the local real-snapshot normalization first")
        cls.clear = fixture.read_bytes()
        if struct.unpack_from("<II", cls.clear) != (normalizer.MAGIC, 39):
            raise unittest.SkipTest("This regression fixture must use metadata schema 39")

    def test_every_header_field_permutation_with_new_keys_and_deltas(self):
        for index, order in enumerate(itertools.permutations(range(3))):
            with self.subTest(order=order):
                encrypted, expected = mangle(self.clear, 8019 + index, order, offset_keys=index % 2 == 1, header_sign=-1 if index % 3 == 2 else 1)
                rebuilt, evidence = normalizer.normalize(encrypted, 39)
                self.assertEqual(rebuilt, self.clear)
                self.assertEqual(evidence["header_length"], expected["header_length"])
                self.assertEqual(evidence["header_xor_key"], expected["header_key"])
                self.assertEqual(tuple(evidence["triple_order"].values()), order)

    def test_malformed_header_is_rejected(self):
        with self.assertRaises(normalizer.DecodeError):
            normalizer.normalize(b"malformed header" * 256, 39)

    def test_standard_metadata_accepts_zero_offsets_for_empty_tables(self):
        plain = bytearray(self.clear)
        for index in range(len(normalizer.NAMES)):
            start, size, count = struct.unpack_from("<III", plain, 8 + index * 12)
            if size == count == 0:
                struct.pack_into("<I", plain, 8 + index * 12, 0)
        result = normalizer.validate_standard(plain, 39)
        self.assertGreater(result["type_definitions"], 0)
        self.assertGreater(result["methods"], 0)

    def test_truncated_sections_are_rejected(self):
        encrypted, _ = mangle(self.clear, 441, (2, 0, 1))
        with self.assertRaises(normalizer.DecodeError):
            normalizer.normalize(encrypted[:len(encrypted) - 1024 * 1024], 39)

    def test_incorrect_type_member_total_is_rejected(self):
        altered = bytearray(self.clear)
        start, size, count = struct.unpack_from("<III", altered, 8 + 19 * 12)
        stride = size // count
        offset = start + stride - 24
        old = struct.unpack_from("<H", altered, offset)[0]
        struct.pack_into("<H", altered, offset, old ^ 1)
        encrypted, _ = mangle(bytes(altered), 671, (1, 2, 0))
        with self.assertRaisesRegex(normalizer.DecodeError, "member counts"):
            normalizer.normalize(encrypted, 39)

    def test_ambiguous_unbounded_layout_is_rejected(self):
        # Multiple plausible empty tail tables can otherwise grow the search
        # exponentially. The recognizer rejects this before using a guess.
        candidates = []
        for index in range(28):
            start, size, count = struct.unpack_from("<III", self.clear, 8 + index * 12)
            candidates.append(normalizer.Section(start - 16, size, count, index * 12))
        tail_start = struct.unpack_from("<I", self.clear, 8 + 28 * 12)[0]
        candidates.extend(normalizer.Section(tail_start - 16, 0, 0, (index + 1000) * 12) for index in range(300))
        with self.assertRaisesRegex(normalizer.DecodeError, "ambiguous"):
            normalizer.find_layouts(self.clear, normalizer.HEADER_SIZE, candidates)


class RealSnapshotRegressionTests(unittest.TestCase):
    def _native_map_case(self, mode):
        game = Path(os.environ.get("CARX_GAME_ASSEMBLY", ROOT / ".work" / "fixtures" / "game" / "GameAssembly.dll"))
        api_map = ROOT / ".work" / "previous" / "doorstop_api.ini"
        if not game.is_file() or not api_map.is_file():
            self.skipTest("Optional local game and generated API map are required")
        import configparser
        sys.path.insert(0, str(SOURCE.parent))
        try:
            from infer_native_decoder import infer_decoder
        except ImportError:
            self.skipTest("Install the native analyzer's pefile/capstone requirements")
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(api_map, encoding="utf-8-sig")
        if mode == "identity":
            parser["Target"]["TimeDateStamp"] = f"{int(parser['Target']['TimeDateStamp'], 16) ^ 1:x}"
        elif mode == "alias":
            parser["Exports"]["il2cpp_init"] = "deliberately_missing_native_export,1"
        else:
            parser.remove_section("Exports")
        with tempfile.TemporaryDirectory(prefix="metadata-api-test-", dir=ROOT / ".work") as temporary:
            bad = Path(temporary) / "bad-api.ini"
            with bad.open("w", encoding="utf-8") as stream:
                parser.write(stream)
            with self.assertRaises(ValueError):
                infer_decoder(game, bad)

    def test_stale_api_target_is_rejected(self):
        self._native_map_case("identity")

    def test_invalid_api_alias_is_rejected(self):
        self._native_map_case("alias")

    def test_incomplete_api_map_is_rejected(self):
        self._native_map_case("incomplete")

    def test_both_real_snapshots_match_all_native_decoded_sections(self):
        snapshots = (
            (ROOT / ".work" / "metadata-research" / "current.native-validated.dat", ROOT / ".work" / "native-metadata" / "current" / "native-decoder.json"),
            (ROOT / ".work" / "metadata-research" / "previous.native-validated.dat", ROOT / ".work" / "native-metadata" / "previous" / "native-decoder.json"),
        )
        if not all(path.is_file() for snapshot in snapshots for path in snapshot):
            self.skipTest("Both optional local game snapshots are required")
        for output, native_path in snapshots:
            with self.subTest(snapshot=output.name):
                raw = output.read_bytes()
                evidence = json.loads(Path(str(output) + ".evidence.json").read_text())
                native = json.loads(native_path.read_text())
                self.assertEqual(evidence["header_length"], native["header"]["length"])
                self.assertEqual(evidence["header_xor_key"], native["header"]["key"])
                for section in native["sections"]:
                    index = next(index for index, item in enumerate(evidence["sections"]) if item["source_start"] == section["file_offset"] and item["size"] == section["byte_size"])
                    start, size, _ = struct.unpack_from("<III", raw, 8 + index * 12)
                    self.assertEqual(normalizer.sha(raw[start:start + size]), section["decoded_sha256"])

    def test_wrong_native_metadata_pair_is_rejected(self):
        current = ROOT / ".work" / "native-metadata" / "current" / "native-decoder.json"
        previous = ROOT / ".work" / "previous" / "diagnostics" / "supplied-inputs" / "global-metadata.dat"
        if not current.is_file() or not previous.is_file():
            self.skipTest("Both optional local game snapshots are required")
        native = json.loads(current.read_text())
        # Native header length/key must agree even when the other snapshot's
        # metadata independently decodes into perfectly valid IL2CPP tables.
        with self.assertRaises(normalizer.DecodeError):
            normalizer.normalize(previous.read_bytes(), 39, native, native["sections"])


if __name__ == "__main__":
    unittest.main()
