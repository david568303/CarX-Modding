# Testing

From the repository root with the Doorstop submodule initialized:

```powershell
python -m pip install -r src/ApiResolver/requirements.txt
python -B -m unittest discover -s tests/ApiResolver -v
python -B -m unittest discover -s tests/MetadataNormalizer -v
python -B -m unittest discover -s tests/NoSymbols -v
.\tests\native\run.ps1
dotnet run --project tests/MetadataBootstrap -c Release
```

Python requirements install analysis packages; no compiler installation is required.
Native tests build synthetic test DLLs with the existing Visual Studio compiler.
No game process is required for these checks.

Private game tests are optional. Set `CARX_API_TEST_GAME_DIR` for native binder tests,
`CARX_API_FIXTURE_DIR` for the two-build canonical mapping/oracle tests and
`CARX_NORMALIZED_FIXTURE` for metadata mutation tests. Fixture directories are ignored.
Never commit the game files, metadata, original API maps or generated interop.

`tools/test-release.ps1` is a local-only, opt-in fresh-extraction game-launch test.
Read its parameters before running it. The symbol-denial option plus stripped debug
metadata verifies that discovery does not depend on PDB files. It copies game inputs
into an isolated test location; do not use it as a public CI job.

A successful pure test run does not establish compatibility with every future game
update. The exact release inventory and source/license checks are recorded with releases.
