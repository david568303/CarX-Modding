#!/usr/bin/env python3
"""Validate release paths, license bytes, source completeness and checksums offline."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_paths(archive: zipfile.ZipFile) -> set[str]:
    names = archive.namelist()
    check(len(names) == len(set(names)), 'Duplicate ZIP paths')
    for name in names:
        path = PurePosixPath(name)
        check(not path.is_absolute() and '..' not in path.parts and ':' not in name and '\\' not in name,
              f'Unsafe ZIP path: {name}')
        check('.git' not in path.parts and '__pycache__' not in path.parts,
              f'Private/generated path in ZIP: {name}')
        check(path.suffix.lower() not in ('.pdb', '.pyc', '.dbt', '.log', '.glb', '.wav'),
              f'Generated/obsolete file in ZIP: {name}')
    check(not any(n.startswith(('assets/', 'src/VehicleVisuals/', 'src/CrabbyPatty/', 'src/Ferrari458/')) for n in names),
          'Loader release contains custom car content')
    check(archive.testzip() is None, 'Corrupt ZIP contents')
    return set(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = root / 'release'
    notice_manifest = json.loads((root / 'licenses/manifest.json').read_text(encoding='utf-8'))
    license_paths = ['LICENSE', 'THIRD-PARTY-NOTICES.md']
    license_paths += [p.relative_to(root).as_posix() for p in sorted((root / 'licenses').rglob('*')) if p.is_file()]
    files = ['BepInEx-Doorstop-NoPDB.zip', f'CarX-Modding-Source-{args.version}.zip']
    records = []
    expected_revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    expected_doorstop = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD:src/Doorstop'], text=True).strip()
    for filename in files:
        path = release / filename
        check(path.is_file(), f'Missing release asset: {filename}')
        data = path.read_bytes()
        checksum = digest(data)
        sidecar = path.with_name(path.name + '.sha256')
        check(sidecar.is_file(), f'Missing checksum: {sidecar.name}')
        check(sidecar.read_text().split() == [checksum, filename], f'Checksum mismatch: {filename}')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = validate_paths(archive)
            for name in license_paths:
                check(name in names, f'{filename}: missing license/notice {name}')
                check(archive.read(name) == (root / name).read_bytes(), f'{filename}: stale license {name}')
            if filename.startswith('BepInEx-'):
                prefix = 'BepInEx/compatibility/'
                package = json.loads(archive.read(prefix + 'package-manifest.json'))
                for item in package['files']:
                    check(item['path'] in names, f"Loader manifest file missing: {item['path']}")
                    payload = archive.read(item['path'])
                    check(len(payload) == item['length'] and digest(payload) == item['sha256'],
                          f"Loader manifest hash mismatch: {item['path']}")
                for key, expected in [('sourceRevision', expected_revision), ('doorstopRevision', expected_doorstop)]:
                    revision = package.get(key) or {}
                    check(revision.get('commit') == expected and revision.get('dirty') is False,
                          f'Loader does not correspond to clean committed {key}')
                for source in notice_manifest['correspondingSources']:
                    name = prefix + 'sources/' + source['file']
                    check(name in names, f'Loader missing corresponding source: {name}')
                    check(digest(archive.read(name)) == source['sha256'], f'Changed corresponding source: {name}')
                with zipfile.ZipFile(io.BytesIO(archive.read(prefix + 'source.zip'))) as source_zip:
                    source_names = validate_paths(source_zip)
                    for name in license_paths + ['src/Doorstop/LICENSE', 'src/Doorstop/COMPATIBILITY.md',
                                                 'src/Doorstop/src/windows/il2cpp_resolver.c',
                                                 'src/MetadataBootstrap/Bootstrap.cs',
                                                 'src/MetadataNormalizer/normalize_metadata.py',
                                                 'src/ApiResolver/prepare_api_map.py']:
                        check(name in source_names, f'Loader source archive missing {name}')
                forbidden = {'GameAssembly.dll', 'UnityPlayer.dll', 'global-metadata.dat',
                             'CarX Drift Racing Online 2.exe', 'doorstop_api.ini'}
                check(not any(PurePosixPath(n).name in forbidden for n in names), 'Loader contains private game inputs')
            else:
                for name in ['SOURCE-REVISION.json', 'src/Doorstop/LICENSE', 'src/Doorstop/build-msvc.ps1',
                             'src/MetadataBootstrap/Bootstrap.cs', 'src/ApiResolver/prepare_api_map.py', 'tools/prepare-licenses.py']:
                    check(name in names, f'Complete source asset missing {name}')
                check(not any(n.startswith(('.work/', 'release/', 'dist/')) for n in names), 'Source contains private build inputs')
                revision = json.loads(archive.read('SOURCE-REVISION.json'))
                check(revision['revision'] == expected_revision and revision['doorstopRevision'] == expected_doorstop,
                      'Complete source asset revision does not match the release commit')
        records.append({'file': filename, 'bytes': len(data), 'sha256': checksum, 'entries': len(names)})
    output = {'format': 1, 'version': args.version, 'licenseFilesPerZip': len(license_paths), 'assets': records}
    (release / 'release-verification.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    (release / 'SHA256SUMS.txt').write_text(''.join(f"{record['sha256']}  {record['file']}\n" for record in records), encoding='ascii')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
