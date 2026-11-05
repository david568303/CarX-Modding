"""Boundary tests for the Nexus archive builder; no game or network is used."""
from pathlib import Path
import importlib.util
import io
import stat
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


if __name__ == "__main__":
    unittest.main()
