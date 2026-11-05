"""Boundary tests for the Nexus archive builder; no game or network is used."""
from pathlib import Path
import argparse
import importlib.util
import io
import json
import stat
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("package_nexus", ROOT / "tools/package-nexus.py")
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


def zip_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return stream.getvalue()


class ArchiveBoundaries(unittest.TestCase):
    def test_paths_reject_escape_and_windows_ambiguous_names(self):
        for name in ("../evil.dll", "/evil.dll", "C:/evil.dll", "dir\\evil.dll", "a//b", "a/./b",
                     "a/../b", "a/evil.", "a/evil ", "NUL.txt", "a/COM1", 'a/"b', "a/\nb", "a/*b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                pack.safe_name(name)

    def test_normal_runtime_path_and_bytecode_are_accepted(self):
        name = "BepInEx/compatibility/python/Lib/encodings/__init__.pyc"
        self.assertEqual(pack.safe_name(name), name)

    def test_duplicate_zip_entries_rejected(self):
        with self.assertWarns(UserWarning):
            data = zip_bytes([("a.txt", b"one"), ("a.txt", b"two")])
        with self.assertRaises(ValueError):
            pack.read_archive(data, "duplicate fixture")

    def test_windows_case_collision_rejected(self):
        data = zip_bytes([("Lib/Foo.pyc", b"one"), ("lib/foo.pyc", b"two")])
        with self.assertRaises(ValueError):
            pack.read_archive(data, "case fixture")

    def test_file_directory_collision_rejected(self):
        data = zip_bytes([("Lib", b"one"), ("Lib/a.pyc", b"two")])
        with self.assertRaises(ValueError):
            pack.read_archive(data, "directory fixture")

    def test_symlink_member_rejected(self):
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            pack.read_archive(zip_bytes([(info, b"../outside")]), "link fixture")

    def test_nested_archive_rejected_even_when_extension_is_disguised(self):
        data = zip_bytes([("hello.txt", b"data")])
        with self.assertRaises(ValueError):
            pack.no_archives({"not-an-archive.dat": data}, "nested fixture")

    def test_archive_extension_rejected_even_if_bytes_are_inert(self):
        with self.assertRaises(ValueError):
            pack.no_archives({"dependency.nupkg": b"inert"}, "extension fixture")

    def test_conflicting_source_merge_rejected(self):
        files = {"src/runtime.c": b"original"}
        with self.assertRaises(ValueError):
            pack.put(files, "src/runtime.c", b"different")
        self.assertEqual(files["src/runtime.c"], b"original")


class ExistingGitHubSources(unittest.TestCase):
    """Exercise runtime-only output and reject sources that do not match its binaries."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        project_commit, doorstop_commit = "a" * 40, "b" * 40
        self.source = {name: ("source: " + name + "\n").encode() for name in (
            "src/Doorstop/LICENSE", "src/Doorstop/src/windows/entrypoint.c",
            "src/MetadataBootstrap/Bootstrap.cs", "src/ApiResolver/prepare_api_map.py",
            "src/MetadataNormalizer/normalize_metadata.py", "tools/build.ps1",
            "tools/build-doorstop.ps1", "Directory.Build.props")}
        self.source["LICENSE"] = b"Project copyright and MIT license\n"
        self.source["licenses/component.txt"] = b"Upstream copyright and LGPL license\n"
        self.source["SOURCE-REVISION.json"] = pack.json_bytes({
            "revision": project_commit, "doorstopRevision": doorstop_commit})
        self.base = {name: ("binary: " + name).encode() for name in (
            "winhttp.dll", "BepInEx/core/BepInEx.MetadataBootstrap.dll",
            "BepInEx/core/BepInEx.Unity.IL2CPP.dll", "dotnet/coreclr.dll", pack.PYTHON + "python.exe")}
        self.base.update({
            "doorstop_config.ini": b"enabled=true\n", "LICENSE": self.source["LICENSE"],
            "licenses/component.txt": self.source["licenses/component.txt"],
            "THIRD-PARTY-NOTICES.md": b"Copyright header\nEvery loader ZIP contains old layout.\n"
                                      b"Replaceable shared DLLs are used.\nCopyright footer\n",
            pack.PYTHON + "python314.zip": zip_bytes([("encodings/__init__.pyc", b"stdlib-bytecode")]),
            pack.PREFIX + "source.zip": zip_bytes(list(self.source.items()))})
        upstream_records = []
        for component, commit in (("BepInEx/BepInEx", "c" * 40), ("BepInEx/Il2CppInterop", "d" * 40)):
            short_name = component.split("/")[-1]
            archive_root = short_name + "-" + commit + "/"
            filename = short_name + "-source.zip"
            archive = zip_bytes([(archive_root + "LICENSE", b"upstream license")])
            self.base[pack.PREFIX + "sources/" + filename] = archive
            upstream_records.append({"component": component, "commit": commit, "file": filename,
                "url": f"https://codeload.github.com/{component}/zip/{commit}",
                "sha256": pack.digest(archive), "archiveRoot": archive_root, "requiredFiles": ["LICENSE"]})
        self.notices = {"notices": [{"file": "component.txt", "sha256": pack.digest(self.base["licenses/component.txt"])}],
                        "correspondingSources": upstream_records}
        self.revisions = {"sourceRevision": {"commit": project_commit, "dirty": False},
                          "doorstopRevision": {"commit": doorstop_commit, "dirty": False}}
        self.args = argparse.Namespace(runtime_zip=self.root / "input.zip", expected_sha256="",
            version="2026.11.05.2", output_dir=self.root / "output", source_zip=self.root / "existing-source.zip",
            source_sha256="", source_url=pack.DEFAULT_SOURCE_URL)
        self.save_source()
        self.save_input()

    def save_source(self):
        data = zip_bytes(list(self.source.items()))
        self.args.source_zip.write_bytes(data)
        self.args.source_sha256 = pack.digest(data)

    def save_input(self):
        self.base["licenses/manifest.json"] = pack.json_bytes(self.notices)
        payload = {name: value for name, value in self.base.items() if name != pack.MANIFEST}
        self.base[pack.MANIFEST] = pack.json_bytes({**self.revisions, "files": pack.file_records(payload)})
        data = zip_bytes(list(self.base.items()))
        self.args.runtime_zip.write_bytes(data)
        self.args.expected_sha256 = pack.digest(data)

    def test_only_runtime_archive_is_created_with_existing_github_source_links(self):
        report = pack.build(self.args)
        archives = list(self.args.output_dir.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        self.assertIn("Runtime-", archives[0].name)
        self.assertEqual([asset["kind"] for asset in report["artifacts"]], ["runtime"])
        self.assertEqual(len(report["correspondingSources"]), 3)
        files = pack.read_archive(archives[0].read_bytes(), "test runtime")
        manifest = json.loads(files[pack.MANIFEST])
        self.assertEqual(manifest["correspondingSources"], report["correspondingSources"])
        self.assertNotIn("sourceCompanion", manifest)
        pack.no_archives(files, "test runtime")
        self.assertFalse(any(name.startswith(("src/", "tools/", "tests/")) for name in files))
        self.assertFalse(any(name.startswith(pack.PREFIX + "sources/") for name in files))
        self.assertEqual(files["LICENSE"], self.base["LICENSE"])
        self.assertEqual(files["licenses/component.txt"], self.base["licenses/component.txt"])
        for name, data in self.base.items():
            if Path(name).suffix.lower() in pack.BINARIES:
                self.assertEqual(files[name], data)
        notices = files["THIRD-PARTY-NOTICES.md"]
        self.assertTrue(notices.startswith(b"Copyright header\n"))
        self.assertTrue(notices.endswith(b"Replaceable shared DLLs are used.\nCopyright footer\n"))
        downloads = files["SOURCE-DOWNLOADS.txt"].decode()
        for source in report["correspondingSources"]:
            self.assertIn(source["url"], downloads)
            self.assertIn(source["sha256"], downloads)
        self.assertNotIn("nexusmods.com", downloads)
        self.assertIn("No separate source download is needed from Nexus", files["README.txt"].decode())

    def test_project_source_checksum_mismatch_rejected(self):
        self.args.source_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "source asset SHA-256 mismatch"):
            pack.build(self.args)
        self.assertFalse(self.args.output_dir.exists())

    def test_stale_source_zip_in_output_rejects_build_without_changing_files(self):
        self.args.output_dir.mkdir()
        stale_source = self.args.output_dir / "CarX-Drift-Racing-Online-2-BepInEx-Sources-old.zip"
        stale_source.write_bytes(zip_bytes([("src/old.cs", b"old source")]))
        before = {path.name: path.read_bytes() for path in self.args.output_dir.iterdir()}
        with self.assertRaisesRegex(ValueError, "Output directory must be new or empty"):
            pack.build(self.args)
        after = {path.name: path.read_bytes() for path in self.args.output_dir.iterdir()}
        self.assertEqual(after, before)

    def test_correct_hash_but_different_source_revision_rejected(self):
        revision = json.loads(self.source["SOURCE-REVISION.json"])
        revision["revision"] = "e" * 40
        self.source["SOURCE-REVISION.json"] = pack.json_bytes(revision)
        self.save_source()
        with self.assertRaisesRegex(ValueError, "source revision does not match"):
            pack.build(self.args)

    def test_matching_revision_but_changed_compiled_source_rejected(self):
        self.source["src/MetadataBootstrap/Bootstrap.cs"] = b"different code\n"
        self.save_source()
        with self.assertRaisesRegex(ValueError, "GitHub source differs from compiled input"):
            pack.build(self.args)

    def test_incomplete_expanded_doorstop_source_rejected(self):
        del self.source["src/Doorstop/src/windows/entrypoint.c"]
        self.save_source()
        with self.assertRaisesRegex(ValueError, "GitHub source differs from compiled input"):
            pack.build(self.args)

    def test_upstream_source_must_use_exact_manifest_commit(self):
        self.notices["correspondingSources"][0]["url"] = "https://codeload.github.com/BepInEx/BepInEx/zip/main"
        self.save_input()
        with self.assertRaisesRegex(ValueError, "not pinned to its exact commit"):
            pack.build(self.args)

    def test_project_source_must_be_explicit_release_asset(self):
        for url in ("https://www.nexusmods.com/carxdriftracingonline2/mods/11?tab=files",
                    "https://github.com/david568303/CarX-Modding/tree/main",
                    "https://github.com/david568303/CarX-Modding/archive/refs/tags/v2026.10.28.1.zip",
                    "http://github.com/a/b/releases/download/v1/source.zip"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                pack.source_download_name(url)


if __name__ == "__main__":
    unittest.main()
