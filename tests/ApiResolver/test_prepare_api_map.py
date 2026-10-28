"""Map publication invariants, independent of symbols or real game fixtures."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ApiResolver"))
import prepare_api_map as prepare


class MapValidationTests(unittest.TestCase):
    def setUp(self):
        names = sorted(prepare.REQUIRED_APIS)
        self.mapping = {name: f"NativeAlias_{index}" for index, name in enumerate(names)}
        self.exports = {alias: 0x1000 + index * 0x20
                        for index, alias in enumerate(self.mapping.values())}
        self.result = {
            "mapping": self.mapping,
            "mapping_count": len(names),
            "canonical_slot_count": len(names),
            "rejected": [], "unmapped": [],
            "witnesses": [{"canonical": name, "actual": alias,
                           "export_rva": hex(self.exports[alias])}
                          for name, alias in self.mapping.items()],
        }

    def test_complete_unique_native_witnesses_are_accepted(self):
        prepare.validate_map(self.result, self.exports)

    def test_critical_api_cannot_be_omitted(self):
        for name in prepare.REQUIRED_APIS:
            with self.subTest(api=name):
                result = copy.deepcopy(self.result)
                result["mapping"].pop(name)
                with self.assertRaisesRegex(ValueError, "Required APIs"):
                    prepare.validate_map(result, self.exports)

    def test_duplicate_aliases_and_inconsistent_counts_are_rejected(self):
        result = copy.deepcopy(self.result)
        names = list(result["mapping"])
        result["mapping"][names[0]] = result["mapping"][names[1]]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            prepare.validate_map(result, self.exports)
        for key in ("mapping_count", "canonical_slot_count"):
            with self.subTest(key=key):
                result = copy.deepcopy(self.result)
                result[key] += 1
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    prepare.validate_map(result, self.exports)

    def test_missing_duplicate_or_extra_witnesses_are_rejected(self):
        mutations = [lambda witnesses: witnesses.pop(),
                     lambda witnesses: witnesses.append(copy.deepcopy(witnesses[0])),
                     lambda witnesses: witnesses.append({"canonical": "il2cpp_extra", "actual": "Extra", "export_rva": "0x1000"})]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = copy.deepcopy(self.result)
                mutation(result["witnesses"])
                with self.assertRaisesRegex(ValueError, "unique native binding witness"):
                    prepare.validate_map(result, self.exports)

    def test_mismatched_alias_rva_or_nonexported_alias_is_rejected(self):
        for field, value in (("actual", "UnrelatedAlias"), ("export_rva", "0x1001")):
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                result["witnesses"][0][field] = value
                with self.assertRaisesRegex(ValueError, "inconsistent loader witness"):
                    prepare.validate_map(result, self.exports)
        exports = dict(self.exports)
        exports.pop(next(iter(exports)))
        with self.assertRaisesRegex(ValueError, "absent export"):
            prepare.validate_map(self.result, exports)

    def test_partial_discovery_and_unsafe_names_are_rejected(self):
        for key in ("rejected", "unmapped"):
            with self.subTest(key=key):
                result = copy.deepcopy(self.result)
                result[key] = ["undetermined"]
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    prepare.validate_map(result, self.exports)
        result = copy.deepcopy(self.result)
        alias = next(iter(result["mapping"].values()))
        result["mapping"]["il2cpp_init"] = alias + "\nOther=Value"
        with self.assertRaisesRegex(ValueError, "Invalid or absent export"):
            prepare.validate_map(result, self.exports)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".work" / "tests" / "api-map-publication"
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(dir=directory, prefix="case-"))

    def test_atomic_write_creates_then_replaces_without_partials(self):
        destination = self.directory / "nested" / "map.ini"
        prepare.atomic_write(destination, "[Target]\nFormat=2\n", "ascii")
        self.assertEqual(destination.read_bytes(), b"[Target]\nFormat=2\n")
        prepare.atomic_write(destination, "replacement\n", "ascii")
        self.assertEqual(destination.read_bytes(), b"replacement\n")
        self.assertEqual(list(destination.parent.glob(".map-*.partial")), [])

    def test_failed_atomic_publication_preserves_existing_file(self):
        destination = self.directory / "map.ini"
        destination.write_text("existing\n")
        with mock.patch.object(prepare.os, "replace", side_effect=OSError("forced publication failure")):
            with self.assertRaisesRegex(OSError, "forced publication"):
                prepare.atomic_write(destination, "replacement\n")
        self.assertEqual(destination.read_text(), "existing\n")
        self.assertEqual(list(self.directory.glob(".map-*.partial")), [])

    def test_outputs_cannot_overwrite_input_binaries_or_each_other(self):
        unity, game = self.directory / "UnityPlayer.dll", self.directory / "GameAssembly.dll"
        unity.write_bytes(b"unity-input")
        game.write_bytes(b"game-input")
        cases = [(game, self.directory / "report.json"),
                 (self.directory / "map.ini", unity),
                 (self.directory / "shared", self.directory / "shared")]
        for output, report in cases:
            with self.subTest(output=output, report=report):
                argv = ["prepare_api_map.py", "--unity", str(unity), "--game", str(game),
                        "--output", str(output), "--json", str(report)]
                with mock.patch.object(sys, "argv", argv), mock.patch.object(prepare, "prepare") as discover:
                    with contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(prepare.main(), 1)
                    discover.assert_not_called()
        self.assertEqual(unity.read_bytes(), b"unity-input")
        self.assertEqual(game.read_bytes(), b"game-input")

    def test_cli_publishes_exact_format_two_discovery_marker(self):
        unity, game = self.directory / "UnityPlayer.dll", self.directory / "GameAssembly.dll"
        unity.write_bytes(b"unity-input")
        game.write_bytes(b"game-input")
        output, report = self.directory / "map.ini", self.directory / "report.json"
        result = {"format": 2, "method": prepare.DISCOVERY_METHOD,
                  "uses_symbols": False, "mapping_count": 3}
        ini = "[Target]\nFormat=2\nDiscovery=binary-loader-schema\n"
        argv = ["prepare_api_map.py", "--unity", str(unity), "--game", str(game),
                "--output", str(output), "--json", str(report)]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(prepare, "prepare", return_value=(result, ini)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(prepare.main(), 0)
        self.assertEqual(output.read_text(), ini)
        self.assertEqual(json.loads(report.read_text()), result)


if __name__ == "__main__":
    unittest.main()
