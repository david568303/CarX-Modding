"""Verify the release-test symbol guard without reading symbols or networking."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SymbolGuardTests(unittest.TestCase):
    def test_forbidden_operations_are_denied_and_ordinary_io_survives(self):
        output = ROOT / ".work" / "tests" / "no-symbols"
        output.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(dir=output, prefix="guard-"))
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).parent)
        code = '''
import pathlib, socket, ctypes, subprocess
checks = [
    ("PDB file", lambda: pathlib.Path("forbidden.pdb").read_bytes()),
    ("symbol DNS", lambda: socket.getaddrinfo("symbolserver.unity3d.com", 443)),
    ("DIA DLL", lambda: ctypes.WinDLL("msdia140.dll")),
    ("DIA helper", lambda: subprocess.run(["pdbsymbols.exe"])),
]
for label, action in checks:
    try:
        action()
    except PermissionError:
        print("PASS", label)
    else:
        raise AssertionError(label)
pathlib.Path("ordinary.txt").write_text("allowed")
print("PASS ordinary I/O")
'''
        process = subprocess.run([sys.executable, "-B", "-c", code],
                                 cwd=directory, env=environment,
                                 text=True, capture_output=True)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(process.stdout.count("PASS "), 5)
        records = [json.loads(line) for line in (directory / "BepInEx" / "cache" /
                   "compatibility" / "no-symbols-audit.jsonl").read_text().splitlines()]
        self.assertEqual(sum(record["kind"] == "installed" for record in records), 1)
        self.assertEqual(sum(record["kind"] == "blocked" for record in records), 4)


if __name__ == "__main__":
    unittest.main()
