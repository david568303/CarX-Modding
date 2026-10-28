"""Native discovery integration checks; mutated images are never loaded/executed."""
import contextlib
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest

import pefile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src' / 'ApiResolver'))
from discover_api_bindings import discover_bindings, DiscoveryError

GAME = Path(os.environ.get('CARX_API_TEST_GAME_DIR', ROOT / '.work' / 'fixtures' / 'game'))


@unittest.skipUnless((GAME / 'UnityPlayer.dll').is_file() and (GAME / 'GameAssembly.dll').is_file(), 'local native game fixtures unavailable')
class NativeDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unity = GAME / 'UnityPlayer.dll'
        cls.game = GAME / 'GameAssembly.dll'
        cls.baseline = discover_bindings(cls.unity, cls.game)

    @contextlib.contextmanager
    def modified_unity(self, modify):
        with tempfile.TemporaryDirectory(prefix='doorstop-native-discovery-') as directory:
            target = Path(directory) / 'UnityPlayer.dll'
            raw = bytearray(self.unity.read_bytes())
            with pefile.PE(str(self.unity), fast_load=True) as pe:
                modify(raw, pe)
            target.write_bytes(raw)
            yield target

    def test_binder_witnesses_are_complete_and_unique(self):
        result = self.baseline
        self.assertGreater(result['binding_count'], 100)
        self.assertFalse(result['pdb_used'])
        self.assertFalse(result['rejected'])
        self.assertEqual(len({binding['actual'] for binding in result['bindings']}), result['binding_count'])
        self.assertEqual(len({binding['slot_rva'] for binding in result['bindings']}), result['binding_count'])
        self.assertTrue(result['resolver_import_witness']['functions'])

    def test_debug_directory_and_codeview_data_removed(self):
        def strip(raw, pe):
            directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[6]
            rva, length = directory.VirtualAddress, directory.Size
            # Erase CodeView payloads too; removing just the header could leave
            # discoverable symbols behind and would be a weaker test.
            pe.parse_data_directories(directories=[6])
            for entry in getattr(pe, 'DIRECTORY_ENTRY_DEBUG', []):
                begin, size = entry.struct.PointerToRawData, entry.struct.SizeOfData
                raw[begin:begin+size] = bytes(size)
            begin = pe.get_offset_from_rva(rva)
            raw[begin:begin+length] = bytes(length)
            struct.pack_into('<II', raw, directory.get_file_offset(), 0, 0)
        with self.modified_unity(strip) as unity:
            result = discover_bindings(unity, self.game)
        self.assertEqual(result['bindings'], self.baseline['bindings'])

    def test_changed_return_store_is_rejected(self):
        store = int(self.baseline['bindings'][0]['store_rva'], 16)
        def change(raw, pe):
            offset = pe.get_offset_from_rva(store)
            self.assertEqual(raw[offset:offset+3], b'\x48\x89\x05')
            raw[offset+2] = 0x0d  # Store RCX instead of the resolver's RAX result.
        with self.modified_unity(change) as unity:
            with self.assertRaises(DiscoveryError):
                discover_bindings(unity, self.game)

    def test_read_only_pointer_slots_are_rejected(self):
        slot = int(self.baseline['bindings'][0]['slot_rva'], 16)
        def change(raw, pe):
            section = pe.get_section_by_rva(slot)
            struct.pack_into('<I', raw, section.get_field_absolute_offset('Characteristics'), section.Characteristics & ~0x80000000)
        with self.modified_unity(change) as unity:
            with self.assertRaises(DiscoveryError):
                discover_bindings(unity, self.game)

    def test_export_resolver_import_mismatch_is_rejected(self):
        def change(raw, pe):
            pe.parse_data_directories(directories=[1])
            symbol = next(symbol for descriptor in pe.DIRECTORY_ENTRY_IMPORT for symbol in descriptor.imports if symbol.name == b'GetProcAddress')
            offset = pe.get_offset_from_rva(symbol.hint_name_table_rva) + 2
            self.assertEqual(raw[offset:offset+14], b'GetProcAddress')
            raw[offset] = ord('X')
        with self.modified_unity(change) as unity:
            with self.assertRaises(DiscoveryError):
                discover_bindings(unity, self.game)

    def test_all_obfuscated_export_names_can_change_without_reference_data(self):
        alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'
        names = [entry['actual'] for entry in self.baseline['bindings']]
        self.assertEqual(len({name[:-1] for name in names}), len(names))
        # Alter final characters, retaining length and PE export-name ordering.
        renamed = {name: name[:-1] + alphabet[(alphabet.index(name[-1]) + 1) % len(alphabet)] for name in names}
        with tempfile.TemporaryDirectory(prefix='doorstop-renamed-exports-') as directory:
            outputs = []
            for source in (self.unity, self.game):
                raw = source.read_bytes()
                for previous, current in renamed.items():
                    needle = previous.encode('ascii') + b'\0'
                    self.assertIn(needle, raw)
                    raw = raw.replace(needle, current.encode('ascii') + b'\0')
                target = Path(directory) / source.name
                target.write_bytes(raw)
                outputs.append(target)
            result = discover_bindings(*outputs)
        self.assertEqual(result['binding_count'], self.baseline['binding_count'])
        for previous, current in zip(self.baseline['bindings'], result['bindings']):
            self.assertEqual(current['actual'], renamed[previous['actual']])
            self.assertEqual(current['slot_rva'], previous['slot_rva'])
            self.assertEqual(current['export_rva'], previous['export_rva'])


if __name__ == '__main__':
    unittest.main()
