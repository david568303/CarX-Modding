#!/usr/bin/env python3
"""Verify committed notices and fetch checksum-pinned corresponding source.

Uses only the Python standard library. Does not install tools or run upstream code.
Large archives are local build inputs under .work/vendor-sources, not Git files.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CarX-Modding-source-preparation"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Source archive destination (default: .work/vendor-sources)")
    parser.add_argument("--check-only", action="store_true", help="Verify notices and local source archives without network access")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "licenses/manifest.json").read_text(encoding="utf-8"))
    target = args.output.resolve() if args.output else root / ".work/vendor-sources"

    for notice in manifest["notices"]:
        path = root / "licenses" / notice["file"]
        if not path.is_file() or sha256(path.read_bytes()) != notice["sha256"]:
            raise SystemExit(f"Missing or changed third-party notice: {path}")
    target.mkdir(parents=True, exist_ok=True)
    for source in manifest["correspondingSources"]:
        path = target / source["file"]
        if not path.is_file():
            if args.check_only:
                raise SystemExit(f"Missing corresponding source: {path}")
            data = download(source["url"])
            if sha256(data) != source["sha256"]:
                raise SystemExit(f"Source download checksum mismatch: {source['url']}")
            # Validate the ZIP before publishing it; do not extract or execute it.
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.testzip() is not None:
                    raise SystemExit(f"Corrupt source archive: {source['file']}")
                for entry in archive.infolist():
                    name = entry.filename
                    if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name or "\\" in name:
                        raise SystemExit(f"Unsafe upstream source ZIP path: {name}")
                prefix = source["archiveRoot"]
                for required in source["requiredFiles"]:
                    if prefix + required not in archive.namelist():
                        raise SystemExit(f"Incomplete upstream source archive: {required}")
            temporary = path.with_suffix(path.suffix + ".download")
            temporary.write_bytes(data)
            temporary.replace(path)
        if sha256(path.read_bytes()) != source["sha256"]:
            raise SystemExit(f"Corresponding source checksum mismatch: {path}")
        print(f"Verified {source['file']}")
    shutil.copyfile(root / "licenses/SOURCE-COMPLIANCE.txt", target / "SOURCE-COMPLIANCE.txt")
    (target / "source-manifest.json").write_text(
        json.dumps({"format": 1, "sources": manifest["correspondingSources"]}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Verified {len(manifest['notices'])} notices; corresponding sources: {target}")


if __name__ == "__main__":
    main()
