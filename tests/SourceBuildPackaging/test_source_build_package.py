"""Source-build package boundaries; synthetic bytes only, no game/network/compiler."""
import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("av_workaround_package", ROOT / "tools/package-av-workaround.py")
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


def make_zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


class SourceBuildPackage(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base = {"winhttp.dll": b"old native", "BepInEx/core/Il2CppInterop.Common.dll": b"old Common",
                     pack.CAPSTONE_DLL: b"old capstone"}
        for i in range(249):
            self.base[f"BepInEx/core/unchanged-{i}.dll"] = f"unchanged binary {i}".encode()
        self.base.update({"LICENSE": b"Project copyright and MIT terms\n", "licenses/upstream.txt": b"Upstream copyright and full LGPL terms\n",
            "README.txt": b"old README", "SOURCE-DOWNLOADS.txt": b"old source links",
            "licenses/SOURCE-COMPLIANCE.txt": b"old policy",
            "THIRD-PARTY-NOTICES.md": b"Project copyright header\n"
                b"| Il2CppInterop | 1.5.3+dbda1cb | LGPL |\n"
                b"| Capstone native disassembler and Python bindings | 5.0.6 | BSD |\n"
                b"| LLVM-derived portions in Capstone | 5.0.6 | LLVM |\n"
                b"The machine-readable [license manifest] old provenance\n"
                b"Copyright holders include ORIGINAL HOLDERS.\n"
                b"This Nexus runtime build links existing corresponding source downloads on GitHub.\nold source links\n"
                b"Replaceable shared DLLs are used. ORIGINAL REPLACEMENT RIGHTS.\n## Release policy\nold release policy\n",
            pack.SITE + "capstone/__init__.py": b"unchanged Python wrapper\n"})
        record = io.StringIO(newline="")
        csv.writer(record, lineterminator="\n").writerows([
            ["capstone/lib/capstone.dll", pack.wheel_hash(self.base[pack.CAPSTONE_DLL]), str(len(self.base[pack.CAPSTONE_DLL]))],
            ["capstone/__init__.py", pack.wheel_hash(self.base[pack.SITE + "capstone/__init__.py"]), str(len(self.base[pack.SITE + "capstone/__init__.py"]))],
            ["capstone-5.0.6.dist-info/RECORD", "", ""]])
        self.base[pack.RECORD] = record.getvalue().encode()
        self.base["licenses/manifest.json"] = pack.json_bytes({"notices": [{"file": "upstream.txt", "sha256": pack.digest(self.base["licenses/upstream.txt"])}]})
        self.replacements = {path: ("new tested " + path).encode() for path in pack.REPLACEMENTS}
        self.expected = {path: pack.digest(data) for path, data in self.replacements.items()}
        self.replacement_patch = mock.patch.object(pack, "REPLACEMENTS", self.expected)
        self.replacement_patch.start()
        self.addCleanup(self.replacement_patch.stop)
        self.profile_patch = mock.patch.dict(pack.CAPSTONE_PROFILE, {"dllSha256": self.expected[pack.CAPSTONE_DLL]})
        self.profile_patch.start()
        self.addCleanup(self.profile_patch.stop)
        self.extra = {path: ("MSVC notice " + path + "\n").encode() for path in pack.NOTICE_NAMES}
        self.notice_records = [{"path": path, "sha256": pack.digest(data), "component": "MSVC fixture",
                                "sourceUrl": "https://visualstudio.microsoft.com/license-terms/"} for path, data in sorted(self.extra.items())]
        self.sources = pack.make_sources("a" * 40)
        self.args = argparse.Namespace(base_zip=self.root / "base.zip", winhttp=self.root / "winhttp.dll",
            common=self.root / "Common.dll", capstone=self.root / "capstone.dll", output_dir=self.root / "output", version="2026.11.07.1")
        for path, local in (("winhttp.dll", self.args.winhttp), ("BepInEx/core/Il2CppInterop.Common.dll", self.args.common), (pack.CAPSTONE_DLL, self.args.capstone)):
            local.write_bytes(self.replacements[path])
        self.base_hash_patch = mock.patch.object(pack, "BASE_SHA256", "")
        self.base_hash_patch.start()
        self.addCleanup(self.base_hash_patch.stop)
        self.inventory_patch = mock.patch.object(pack, "BASE_INVENTORY_SHA256", "")
        self.inventory_patch.start()
        self.addCleanup(self.inventory_patch.stop)
        self.save_base()

    def save_base(self):
        payload = {name: data for name, data in self.base.items() if name != pack.MANIFEST}
        self.base[pack.MANIFEST] = pack.json_bytes({"format": 1, "profile": "nexus-runtime", "version": "2026.11.05.2",
            "createdUtc": "2026-11-05T09:46:42.373396+00:00",
            "sourceRevision": {"commit": pack.BASE_SOURCE_COMMIT, "dirty": False}, "files": pack.zipio.file_records(payload)})
        self.base_data = make_zip(self.base)
        self.args.base_zip.write_bytes(self.base_data)
        pack.BASE_SHA256 = pack.digest(self.base_data)
        pack.BASE_INVENTORY_SHA256 = pack.canonical_base_inventory(self.base, json.loads(self.base[pack.MANIFEST]))

    def repack(self, replacements=None, sources=None, extra=None, notices=None):
        return pack.repack(self.base_data, self.replacements if replacements is None else replacements,
            self.sources if sources is None else sources, self.extra if extra is None else extra,
            self.notice_records if notices is None else notices, self.args.version)

    def test_only_three_binary_changes_and_all_other_bytes_preserved(self):
        files, report = self.repack()
        self.assertEqual(set(files) - set(self.base), pack.NOTICE_NAMES)
        changed_binaries = {n for n in self.base if Path(n).suffix in pack.zipio.BINARIES and self.base[n] != files[n]}
        self.assertEqual(changed_binaries, set(self.expected))
        self.assertEqual(report["unchangedExecutableFiles"], 249)
        for name, data in self.base.items():
            if name not in pack.TEXT_CHANGES | set(self.expected):
                self.assertEqual(files[name], data, name)
        self.assertEqual(files["LICENSE"], self.base["LICENSE"])
        self.assertEqual(files["licenses/upstream.txt"], self.base["licenses/upstream.txt"])
        self.assertEqual(files["licenses/manifest.json"], self.base["licenses/manifest.json"])
        self.assertIn(b"Copyright holders include ORIGINAL HOLDERS.", files["THIRD-PARTY-NOTICES.md"])
        self.assertIn(b"ORIGINAL REPLACEMENT RIGHTS.", files["THIRD-PARTY-NOTICES.md"])

    def test_wheel_record_uses_urlsafe_base64_hash_without_padding(self):
        files, _ = self.repack()
        rows = {r[0]: r[1:] for r in csv.reader(io.StringIO(files[pack.RECORD].decode()))}
        wanted = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(self.replacements[pack.CAPSTONE_DLL]).digest()).decode().rstrip("=")
        self.assertEqual(rows["capstone/lib/capstone.dll"], [wanted, str(len(self.replacements[pack.CAPSTONE_DLL]))])
        self.assertNotIn("=", wanted.split("=", 1)[1])
        self.assertEqual(rows["capstone-5.0.6.dist-info/RECORD"], ["", ""])
        before = {r[0]: r[1:] for r in csv.reader(io.StringIO(self.base[pack.RECORD].decode()))}
        self.assertEqual(rows["capstone/__init__.py"], before["capstone/__init__.py"])

    def test_one_runtime_zip_and_complete_new_manifest(self):
        report = pack.package(self.args, self.sources, self.extra, self.notice_records)
        archives = list(self.args.output_dir.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        self.assertIn("Runtime-", archives[0].name)
        self.assertFalse(report["sourceArchiveIncluded"])
        files = pack.zipio.read_archive(archives[0].read_bytes(), "output fixture")
        manifest = json.loads(files[pack.MANIFEST])
        self.assertEqual({r["path"] for r in manifest["files"]}, set(files) - {pack.MANIFEST})
        for entry in manifest["files"]:
            self.assertEqual(pack.digest(files[entry["path"]]), entry["sha256"])
            self.assertEqual(len(files[entry["path"]]), entry["length"])
        links = files["SOURCE-DOWNLOADS.txt"].decode()
        self.assertIn(pack.NATIVE_COMMIT, links)
        self.assertIn("a" * 40, links)
        self.assertNotIn("/main", links)
        self.assertNotIn("/fix/", links)
        self.assertIn("separate complete UnityDoorstop snapshot", links)
        pack.zipio.no_archives(files, "output fixture")

    def test_wrong_base_hash_rejected(self):
        changed = dict(self.base)
        changed["BepInEx/core/unchanged-0.dll"] += b"payload alteration"
        manifest = json.loads(changed[pack.MANIFEST])
        manifest["files"] = pack.zipio.file_records({n: d for n, d in changed.items() if n != pack.MANIFEST})
        changed[pack.MANIFEST] = pack.json_bytes(manifest)
        with self.assertRaisesRegex(ValueError, "immutable audited runtime"):
            pack.repack(make_zip(changed), self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_manifest_tampering_rejected_even_if_archive_is_explicitly_trusted(self):
        altered = dict(self.base)
        altered["BepInEx/core/unchanged-0.dll"] += b"tamper"
        data = make_zip(altered)
        with mock.patch.object(pack, "BASE_SHA256", pack.digest(data)), self.assertRaisesRegex(ValueError, "manifest mismatch"):
            pack.repack(data, self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_unmanifested_payload_rejected(self):
        altered = dict(self.base)
        altered["unlisted.txt"] = b"unexpected"
        data = make_zip(altered)
        with mock.patch.object(pack, "BASE_SHA256", pack.digest(data)), self.assertRaisesRegex(ValueError, "unmanifested"):
            pack.repack(data, self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_unexpected_replacement_path_rejected(self):
        values = dict(self.replacements)
        values["BepInEx/core/other.dll"] = b"unapproved"
        with self.assertRaisesRegex(ValueError, "three approved replacement paths"):
            self.repack(replacements=values)

    def test_unexpected_replacement_bytes_rejected(self):
        values = dict(self.replacements)
        values["winhttp.dll"] += b"changed"
        with self.assertRaisesRegex(ValueError, "Unexpected replacement hash"):
            self.repack(replacements=values)

    def test_missing_replacement_rejected(self):
        values = dict(self.replacements)
        del values[pack.CAPSTONE_DLL]
        with self.assertRaisesRegex(ValueError, "three approved replacement paths"):
            self.repack(replacements=values)

    def test_wheel_record_must_match_original_dll(self):
        self.base[pack.RECORD] = self.base[pack.RECORD].replace(pack.wheel_hash(self.base[pack.CAPSTONE_DLL]).encode(), b"sha256=wrong")
        self.save_base()
        with self.assertRaisesRegex(ValueError, "Base wheel RECORD"):
            self.repack()

    def test_stale_output_source_archive_is_not_overwritten_or_distributed(self):
        self.args.output_dir.mkdir()
        old_source = self.args.output_dir / "Sources-old.zip"
        old_source.write_bytes(b"preserve existing file")
        with self.assertRaisesRegex(ValueError, "fresh or empty"):
            pack.package(self.args, self.sources, self.extra, self.notice_records)
        self.assertEqual(list(self.args.output_dir.iterdir()), [old_source])
        self.assertEqual(old_source.read_bytes(), b"preserve existing file")

    def test_existing_license_cannot_be_overwritten(self):
        name = sorted(pack.NOTICE_NAMES)[0]
        self.base[name] = b"previously present license"
        self.save_base()
        with self.assertRaisesRegex(ValueError, "notice overwrite"):
            self.repack()

    def test_unexpected_notice_paths_or_empty_notice_set_rejected(self):
        with self.assertRaisesRegex(ValueError, "notice paths"):
            self.repack(extra={}, notices=[])
        values = dict(self.extra)
        values["licenses/unapproved.txt"] = b"unapproved"
        with self.assertRaisesRegex(ValueError, "notice paths"):
            self.repack(extra=values)

    def test_moving_source_url_rejected(self):
        sources = json.loads(json.dumps(self.sources))
        sources["records"][0]["url"] = "https://github.com/david568303/CarX-Modding/tree/main"
        with self.assertRaisesRegex(ValueError, "exact tested public GitHub revisions"):
            self.repack(sources=sources)

    def test_path_traversal_and_nested_archives_rejected(self):
        for name in ("../escape.dll", "inner.zip"):
            with self.subTest(name=name):
                altered = dict(self.base)
                altered[name] = b"untrusted"
                data = make_zip(altered)
                with mock.patch.object(pack, "BASE_SHA256", pack.digest(data)), self.assertRaises(ValueError):
                    pack.repack(data, self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_production_source_collection_blocks_a_pending_capstone_profile(self):
        with mock.patch.dict(pack.CAPSTONE_PROFILE, {"finalTestedProfile": False}), mock.patch.object(pack, "git") as git:
            with self.assertRaisesRegex(ValueError, "final tested Capstone"):
                pack.collect_sources(self.root)
            git.assert_not_called()

    def write_notice_spec(self, records):
        (self.root / "licenses").mkdir(exist_ok=True)
        for name, data in self.extra.items():
            (self.root / name).write_bytes(data)
        (self.root / "licenses/source-build-notices.json").write_bytes(pack.json_bytes({"format": 1, "files": records}))

    def test_committed_notice_spec_requires_exact_paths_and_bytes(self):
        self.write_notice_spec(self.notice_records)
        files, records = pack.load_notices(self.root)
        self.assertEqual(files, self.extra)
        self.assertEqual(records, self.notice_records)
        wrong = json.loads(json.dumps(self.notice_records))
        wrong[0]["sha256"] = "0" * 64
        self.write_notice_spec(wrong)
        with self.assertRaisesRegex(ValueError, "notice checksum mismatch"):
            pack.load_notices(self.root)
        self.write_notice_spec([])
        with self.assertRaisesRegex(ValueError, "three approved MSVC"):
            pack.load_notices(self.root)

    def test_notice_source_url_must_identify_microsoft(self):
        for url in ("http://visualstudio.microsoft.com/license", "https://visualstudio.microsoft.com.evil.example/license"):
            with self.subTest(url=url):
                records = json.loads(json.dumps(self.notice_records))
                records[0]["sourceUrl"] = url
                self.write_notice_spec(records)
                with self.assertRaisesRegex(ValueError, "official Microsoft"):
                    pack.load_notices(self.root)

    def test_native_capstone_version_is_distinguished_from_unchanged_python_bindings(self):
        with mock.patch.dict(pack.CAPSTONE_PROFILE, {"nativeVersion": "5.0.9", "patchPath": None, "patchSha256": None, "extraFiles": []}):
            sources = pack.make_sources("a" * 40)
            files, _ = self.repack(sources=sources)
            self.assertIn(b"Native 5.0.9 source build; Python bindings 5.0.6", files["THIRD-PARTY-NOTICES.md"])
            self.assertIn(b"Capstone native version: 5.0.9", files["SOURCE-DOWNLOADS.txt"])
            self.assertFalse(any(h["path"].startswith("patches/") for h in sources["helpers"]))

    def test_resource_and_cmake_build_inputs_have_exact_commit_links_and_hashes(self):
        helpers = {r["path"]: r for r in self.sources["helpers"]}
        for record in pack.maintained_capstone_files():
            helper = helpers[record["path"]]
            self.assertEqual(helper["sha256"], record["sha256"])
            self.assertEqual(helper["url"], "https://github.com/" + pack.ROOT_REPO + "/blob/" + "a" * 40 + "/" + record["path"])
        files, _ = self.repack()
        source_text = files["SOURCE-DOWNLOADS.txt"].decode()
        for record in pack.maintained_capstone_files():
            self.assertIn(record["sha256"], source_text)

    def test_maintained_build_input_cannot_escape_its_source_directory(self):
        with mock.patch.dict(pack.CAPSTONE_PROFILE, {"extraFiles": [{"path": "../private-file", "sha256": "a" * 64}]}):
            with self.assertRaises(ValueError):
                pack.make_sources("a" * 40)

    def test_reconstructed_base_accepts_only_creation_time_and_container_differences(self):
        reconstructed = dict(self.base)
        manifest = json.loads(reconstructed[pack.MANIFEST])
        manifest["createdUtc"] = "2026-11-07T03:00:01+00:00"
        reconstructed[pack.MANIFEST] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
            archive.comment = b"Reconstructed container metadata"
            for name in reversed(list(reconstructed)):
                archive.writestr(name, reconstructed[name])
        data = stream.getvalue()
        self.assertNotEqual(pack.digest(data), pack.BASE_SHA256)
        files, report = pack.repack(data, self.replacements, self.sources, self.extra, self.notice_records, self.args.version)
        self.assertEqual(report["basePayloadInventorySha256"], pack.BASE_INVENTORY_SHA256)
        self.assertEqual(report["baseSha256"], pack.digest(data))
        self.assertEqual(report["auditedBaseZipSha256"], pack.BASE_SHA256)
        self.assertEqual(files["BepInEx/core/unchanged-0.dll"], self.base["BepInEx/core/unchanged-0.dll"])

    def test_equivalent_container_cannot_change_source_provenance(self):
        reconstructed = dict(self.base)
        manifest = json.loads(reconstructed[pack.MANIFEST])
        manifest["createdUtc"] = "2026-11-07T03:00:01+00:00"
        manifest["sourceRevision"]["commit"] = "e" * 40
        reconstructed[pack.MANIFEST] = pack.json_bytes(manifest)
        with self.assertRaisesRegex(ValueError, "payload inventory"):
            pack.repack(make_zip(reconstructed), self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_equivalent_container_cannot_change_version_or_other_manifest_fields(self):
        for key, value in (("version", "2026.11.05.3"), ("unexpectedProvenance", "new value")):
            with self.subTest(key=key):
                reconstructed = dict(self.base)
                manifest = json.loads(reconstructed[pack.MANIFEST])
                manifest[key] = value
                reconstructed[pack.MANIFEST] = pack.json_bytes(manifest)
                with self.assertRaises(ValueError):
                    pack.repack(make_zip(reconstructed), self.replacements, self.sources, self.extra, self.notice_records, self.args.version)

    def test_ignored_creation_time_must_still_be_a_real_utc_timestamp(self):
        for value in ("not a timestamp", "2026-11-07T03:00:01+01:00", None):
            with self.subTest(value=value):
                reconstructed = dict(self.base)
                manifest = json.loads(reconstructed[pack.MANIFEST])
                manifest["createdUtc"] = value
                reconstructed[pack.MANIFEST] = pack.json_bytes(manifest)
                with self.assertRaises(ValueError):
                    pack.repack(make_zip(reconstructed), self.replacements, self.sources, self.extra, self.notice_records, self.args.version)


if __name__ == "__main__":
    unittest.main()
