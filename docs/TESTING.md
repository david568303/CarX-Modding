# Testing

From the repository root with the Doorstop submodule initialized:

```powershell
python -m pip install -r src/ApiResolver/requirements.txt
python -B -m unittest discover -s tests/ApiResolver -v
python -B -m unittest discover -s tests/MetadataNormalizer -v
.\tests\native\run.ps1
$runtime = .\tools\prepare-bepinex.ps1
$core = Join-Path $runtime 'BepInEx/core'
dotnet run --project tests/MetadataBootstrap -c Release "-p:BepInExCoreDirectory=$core"
```

The Python tests exercise the reference analyzers. They are developer tools.
Native tests build synthetic test DLLs with the existing Visual Studio compiler.
No game process is required for these checks.

The source-build loader has a separate [synthetic host smoke suite](../tests/NativeLoaderSmoke/README.md).
Supply explicit candidate/baseline DLLs and fresh output directories to verify proxy
forwarding, unload/reload/rebase behavior and enabled import hooks without starting
CoreCLR or the game.

The [Dobby comparison suite](../tests/DobbyCompatibility/README.md) builds fixture
hosts and exercises the actual BepInEx native-detour wrapper on isolated CoreCLR
6.0.7 inputs. It compares original/rebuilt DLL behavior without starting the game.
Two existing conditional-branch relocation failures remain failures on both
libraries; its nonzero correctness exit is reported separately from the absence
of new regressions in the exercised cases. See that suite's README for commands,
expected results and scope.

Private game tests are optional. Set `CARX_API_TEST_GAME_DIR` for native binder tests,
`CARX_API_FIXTURE_DIR` for the two-build canonical mapping/oracle tests and
`CARX_NORMALIZED_FIXTURE` for metadata mutation tests. Fixture directories are ignored.
Never commit the game files, metadata, original API maps or generated interop.

`tools/test-release.ps1` is a local-only, opt-in fresh-extraction game-launch test.
Run it with `-StripDebugDirectories` to verify discovery with the copied PE debug
metadata removed. It copies game inputs into an isolated test location and checks
that the game starts BepInEx and loads a verification plugin.

A successful pure test run does not establish compatibility with every future game
update. The exact release inventory and source/license checks are recorded with releases.
