# Symbol-free IL2CPP API discovery

`discover_api_bindings.py` finds the engine's native export-binding routine
using executable string references, x64 unwind boundaries, call-result stores,
and the Windows `GetProcAddress` import. It extracts current export names and
pointer slots from the paired binaries. It does not read symbols, CodeView
records, a saved alias map, or another version of the game.

`canonical_api_schema.py` assigns public API identities only after a compiler
feature profile and distributed native semantic checks agree. The independent
schema describes the Unity native C API, rather than any game's exports. Its
241 functional declarations come from an unrelated Unity-generated SDK header;
seven are guarded by `IL2CPP_ENABLE_PROFILER`, giving enabled/disabled profiles.
The 222 declarations shared with Unity Technologies' first-party sample header
have identical relative declaration order. Resource provenance and SHA-256
hashes are recorded in `il2cpp-api-schema.json`.

Count and order alone are insufficient. The validator checks native init and
UTF16 conversion, shared initialization state, the four-pointer invocation ABI,
object/string/array layout, related field/method/property accessors, enum bits,
GC control relationships, Windows TLS/debugger calls, attribute initialization,
and the self-reported class user-data offset. Current inputs pass 55 checks
covering 62 API identities, with at most 17 declarations between anchors.
Unknown counts, altered critical functions, mismatched images, and unsupported
native instruction forms are refused before publishing an alias map.

The numeric object-member displacements are ordinary Windows-x64 IL2CPP ABI
contracts and relationships, not game-image addresses. Addresses and renamed
exports in diagnostic output are discovered from the current inputs.

The supported compiler profiles are not a promise about all future Unity API
redesigns. A changed declaration contract or unrecognized implementation needs
an explicit schema/validator update; there is no PDB fallback.

Tests compare both supplied builds with historical test-only oracles, and
reject same-count swaps of getters, init functions, and invoke functions. Those
oracles are not imported by production code or included in the installable ZIP.
