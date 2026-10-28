# UnityDoorstop publication diff

Prepared 2026-10-28 against the original committed clone. The resulting history
is published at https://github.com/david568303/UnityDoorstop on `carx-compatibility`.

- Upstream: https://github.com/NeighTools/UnityDoorstop.git
- Original clone: `.work/previous/vendor/UnityDoorstop`
- Clean base: `1c3ece1f1e6c20f4aa74d5402baabf8a0098d282` (201 upstream commits retained)
- Publication branch: `carx-compatibility`
- Publication head: `ad3edbebd071449c22845c18a12326d49a437c89`
- Full patch: `doorstop-diff.patch`
- Patch SHA-256: `2be05a5e9e16e654efbdb0c4c0aa1c93a5de4de2e6ebb4243093d97a4d3e38d5`

The original clone has dirty older working-tree edits. This branch was created
from its committed base, then populated only with maintained final source.
It does not preserve experimental intermediate code or removed implementations.
No `.dbt`/DBT source, PDB resolver, generated game API map, game binaries, game
metadata, build outputs, or test caches have been committed.

## Sequential commits

```text
e31ba8925149bbce612cef03f05372e04bdc6335 Add validated IL2CPP export maps and automatic refresh
71639c436b6ce4d2735c2404fd73888b43ac68df Resolve renamed native IL2CPP exports during initialization
b42f2cafd9e644be6bd6445e7207589092305a58 Resolve canonical IL2CPP APIs from CoreCLR
ad3edbebd071449c22845c18a12326d49a437c89 Document compatibility changes and add existing-tools MSVC build
```

The first three commits introduce the final native implementation. The fourth
adds dated modification notices, build tooling and documentation. Each of the
six native C/header files equals the maintained final source after removing
only its new five-line modification notice. No functional native source changes
were introduced during publication preparation.

## Final maintained-code delta against upstream

Ignoring line-ending/final-newline differences, before publication notices:

| Path | Added | Removed |
| --- | ---: | ---: |
| `src/bootstrap.c` | 15 | 0 |
| `src/windows/entrypoint.c` | 21 | 1 |
| `src/windows/wincrt.c` | 2 | 1 |
| `src/windows/il2cpp_resolver.c` | 69 | 0 |
| `src/windows/il2cpp_resolver.h` | 11 | 0 |
| `src/windows/map_refresh.c` | 114 | 0 |

No upstream file is deleted. `LICENSE` remains unchanged; the GNU LGPL 2.1 text
and upstream notices are retained. Added or modified native C/header files have
modification notices dated 2026-10-28. `CHANGES.md` and `COMPATIBILITY.md` identify
the upstream base and explain the native integration.

## Complete publication diff statistics

```text
 CHANGES.md                    |  21 ++++++++
 COMPATIBILITY.md              |  67 ++++++++++++++++++++++++
 README.md                     |   4 ++
 build-msvc.ps1                |  58 ++++++++++++++++++++
 src/bootstrap.c               |  22 +++++++-
 src/windows/entrypoint.c      |  27 +++++++++-
 src/windows/il2cpp_resolver.c |  74 ++++++++++++++++++++++++++
 src/windows/il2cpp_resolver.h |  16 ++++++
 src/windows/map_refresh.c     | 119 ++++++++++++++++++++++++++++++++++++++++++
 src/windows/wincrt.c          |  10 +++-
 10 files changed, 414 insertions(+), 4 deletions(-)
```

## Validation

- `git diff --check`: passed.
- Working tree after the fourth commit: clean.
- `build-msvc.ps1 -Release`: compiled and linked `build/msvc-x64/winhttp.dll`
  successfully using the existing Visual Studio 2026 x64 tools and MASM.
- The compiler reported existing warnings in upstream code (MAX_PATH macro,
  types/narrowing, and `fclose` missing return). No compiler was installed.
- Native resolver fixture suite, compiled against this publication fork:
  **29 passed, 0 failed**. It loads synthetic fixture DLLs only.
- No game session was opened or closed for these publication checks.
- This preparation does not repeat the earlier full in-game integration test.

## Other source checkouts

No BepInEx source checkout was found: the project uses an official unchanged
BepInEx distribution plus separate new compatibility sources.
`.work/vendor/Cpp2IL` is a clean research/parser checkout at
`b5ad444b82267cb1e4b88b8b373c008105bdea52`, not a modified source fork.
The API resolver, metadata normalizer, metadata bootstrap, integration tests and
release packaging belong in the integration repository. They are not added to
this native upstream-history fork.
