# Metadata normalization

The normalizer converts recognized MFuscator metadata into the ordinary IL2CPP
metadata format consumed by the Cpp2IL library bundled with BepInEx. It reads the
original GameAssembly, engine, API map and metadata without modifying them.

```powershell
python -B normalize_metadata.py --game "D:\SteamLibrary\steamapps\common\CarX Drift Racing Online 2\GameAssembly.dll" --metadata "D:\SteamLibrary\steamapps\common\CarX Drift Racing Online 2\CarX Drift Racing Online 2_Data\il2cpp_data\Metadata\global-metadata.dat" --api-map "doorstop_api.ini" --output "BepInEx\cache\metadata\global-metadata.dat"
```

Install the pinned dependencies from `requirements.txt` in the Python runtime
used by the bootstrap. Both Python files must be deployed together. The normal
launcher supplies all paths automatically. Successful conversion writes the
separate output and an `.evidence.json` sidecar. Failures return a nonzero exit
code and leave source inputs intact.

The implementation discovers each input's header length, rotating XOR key,
shuffled offset/size/count field order, real triples among decoys, signed offset
adjustments and section XOR keys. The canonical table order and record schemas
come from the IL2CPP metadata format. It derives variable-width index sizes from
the actual table counts. It contains no CarX version checks, randomized export
names, game RVAs, captured XOR keys or captured metadata field offsets.

The companion native analyzer independently follows the verified init API's
call graph and recognizes the game's decoder instructions. Before accepting a
result, the normalizer checks that both approaches agree on the header, field
placement, source ranges and every byte of all seven encrypted tables. It also
checks member totals, image totals, string indices, literal offsets, attribute
ranges and virtual-call range coverage. Ambiguous reconstruction is rejected.

Currently supported public metadata schemas are 38 and 39, including already
standard metadata. This is a format constraint rather than a list of game
versions. A future engine or obfuscator that changes the format or native
decoder instruction shapes will produce a clear failure requiring support for
the new format. It is not possible to promise compatibility with unknown future
formats.

Tests under `tests/MetadataNormalizer` use optional local private fixtures and
generate changed keys, both header XOR directions, all six field permutations,
new decoys, new header lengths, changed offset adjustments and both offset-based
and size-based section key families. Game binaries and metadata are not included
with the source. `tests/MetadataProbe` independently verifies the normalized
files using the exact LibCpp2IL assembly supplied with BepInEx.

Format research references:

- [Cpp2IL's MFuscator support](https://github.com/SamboyCoding/Cpp2IL/blob/development/Cpp2IL.Plugin.Mfuscator/MfuscatorSupportPlugin.cs)
- [IL2CPP metadata section headers](https://github.com/SamboyCoding/Cpp2IL/blob/development/LibCpp2IL/Metadata/Il2CppGlobalMetadataSectionHeader.cs)
- [Variable-width index schemas](https://github.com/SamboyCoding/Cpp2IL/blob/development/LibCpp2IL/Metadata/Il2CppVariableWidthIndex.cs)

Cpp2IL is maintained by SamboyCoding and contributors under the MIT license.
