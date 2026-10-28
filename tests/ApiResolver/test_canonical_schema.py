"""Schema alignment must be established by code evidence, not binder count alone."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src' / 'ApiResolver'))
from canonical_api_schema import canonicalize_bindings, load_schema, schema_profiles, SchemaError
from discover_api_bindings import discover_bindings


class DeclarationSchemaTests(unittest.TestCase):
    def test_contract_has_only_public_declarations_and_compiler_features(self):
        schema = load_schema()
        self.assertTrue(schema['sources'][1]['identical_relative_order'])
        self.assertGreater(schema['sources'][1]['shared_declarations'], 200)
        for declaration in schema['functions']:
            self.assertEqual(set(declaration), {'name', 'return_type', 'parameters', 'group', 'guard'})
            self.assertTrue(declaration['name'].startswith('il2cpp_'))
        profiles = list(schema_profiles(schema))
        self.assertEqual(len(profiles), 2)
        disabled = profiles[0][1]
        enabled = profiles[1][1]
        self.assertEqual([f for f in enabled if f['guard'] is None], disabled)
        self.assertTrue(all(f['name'].startswith('il2cpp_profiler_') for f in enabled if f['guard']))


class RealImageCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = Path(os.environ.get('CARX_API_FIXTURE_DIR', ROOT / '.work' / 'previous'))
        cls.older = cls.current / 'diagnostics' / 'supplied-inputs'
        required = [cls.current / name for name in ('UnityPlayer.dll', 'GameAssembly.dll', 'diagnostics/api-map.json')]
        required += [cls.older / name for name in ('UnityPlayer.dll', 'GameAssembly.dll', 'api-map.json')]
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest('Private native fixtures unavailable; set CARX_API_FIXTURE_DIR to run these checks')
        cls.current_discovery = discover_bindings(cls.current / 'UnityPlayer.dll', cls.current / 'GameAssembly.dll')
        cls.current_result = canonicalize_bindings(cls.current / 'UnityPlayer.dll', cls.current / 'GameAssembly.dll', cls.current_discovery)

    def mapping_mutation(self, first, second):
        discovery = copy.deepcopy(self.current_discovery)
        names = [w['canonical'] for w in self.current_result['witnesses']]
        one, two = discovery['bindings'][names.index(first)], discovery['bindings'][names.index(second)]
        for key in ('actual', 'export_rva'):
            one[key], two[key] = two[key], one[key]
        return discovery

    def test_current_contract_matches_independent_test_oracle(self):
        oracle = json.loads((self.current / 'diagnostics' / 'api-map.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(self.current_result['mapping'], oracle['mapping'])
        validation = self.current_result['semantic_validation']
        self.assertTrue(validation['passed'])
        self.assertGreaterEqual(validation['check_count'], 50)
        self.assertGreaterEqual(validation['anchored_api_count'], 60)
        self.assertFalse(self.current_result['uses_symbols'])

    def test_older_build_changes_aliases_but_uses_same_contract(self):
        discovery = discover_bindings(self.older / 'UnityPlayer.dll', self.older / 'GameAssembly.dll')
        result = canonicalize_bindings(self.older / 'UnityPlayer.dll', self.older / 'GameAssembly.dll', discovery)
        oracle = json.loads((self.older / 'api-map.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(result['mapping'], oracle['mapping'])
        self.assertEqual(set(result['mapping']), set(self.current_result['mapping']))
        self.assertNotEqual(result['mapping'], self.current_result['mapping'])

    def test_unknown_api_count_is_not_guessed(self):
        discovery = copy.deepcopy(self.current_discovery)
        discovery['bindings'].pop()
        discovery['binding_count'] -= 1
        with self.assertRaisesRegex(SchemaError, 'compiler-feature profile'):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)

    def test_same_count_wrong_getter_order_is_refused(self):
        discovery = self.mapping_mutation('il2cpp_object_get_class', 'il2cpp_string_chars')
        with self.assertRaisesRegex(SchemaError, 'object_get_class'):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)

    def test_same_count_wrong_initialization_contract_is_refused(self):
        discovery = self.mapping_mutation('il2cpp_init', 'il2cpp_init_utf16')
        with self.assertRaises(ValueError):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)

    def test_same_count_wrong_invoke_contract_is_refused(self):
        discovery = self.mapping_mutation('il2cpp_runtime_invoke', 'il2cpp_runtime_invoke_convert_args')
        with self.assertRaisesRegex(ValueError, 'Runtime::Invoke'):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)

    def test_same_count_corrupt_export_witness_is_refused(self):
        discovery = copy.deepcopy(self.current_discovery)
        discovery['bindings'][0]['export_rva'] = hex(int(discovery['bindings'][0]['export_rva'], 16) + 1)
        with self.assertRaisesRegex(SchemaError, 'export address'):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)

    def test_binary_identity_change_is_refused(self):
        discovery = copy.deepcopy(self.current_discovery)
        discovery['game_assembly_sha256'] = '0' * 64
        with self.assertRaisesRegex(SchemaError, 'binary images'):
            canonicalize_bindings(self.current / 'UnityPlayer.dll', self.current / 'GameAssembly.dll', discovery)


if __name__ == '__main__':
    unittest.main()
