# Native loader smoke tests

These Windows x64 tests exercise a supplied Doorstop DLL in small synthetic hosts.
They require installed Visual Studio x64 C++ tools and the Windows SDK. They install
no compiler and use no game files, CoreCLR runtime, Python helper, network request or
managed bootstrap. No game process is launched or closed.

Run from the repository root in PowerShell. Supply explicit existing DLL paths and
new build directories; the runners copy inputs and write all generated files beneath
those directories. Existing files are never overwritten. Keep output under ignored
`.work/`, outside any game installation:

```powershell
.\tests\NativeLoaderSmoke\run-host-smoke.ps1 `
  -Doorstop C:\path\to\candidate\winhttp.dll `
  -Baseline C:\path\to\previous\winhttp.dll `
  -BuildRoot .\.work\native-smoke\forwarding-new

.\tests\NativeLoaderSmoke\run-enabled-smoke.ps1 `
  -Doorstop C:\path\to\candidate\winhttp.dll `
  -BuildRoot .\.work\native-smoke\enabled-new
```

The disabled-loader host performs **110 checks**: compare forwarding behavior against
the real System32 `winhttp.dll`, including arguments beyond the four register slots;
verify requested absolute DLLs are distinct images, execute a relocated image, and
unload/reload the candidate three times. URL parsing uses `example.invalid` as data
and makes no network connection. Provide the previous working loader as `-Baseline`
to retain a real before/after comparison.

The enabled-loader host performs **59 checks** against a locally compiled synthetic
`GameAssembly.dll`. It checks four own-process IAT hooks, the stock canonical
initialization wrapper, ordinal and ordinary lookup passthrough, command-line
preservation, and private handle closing. It exercises a valid x64 name pointer
whose low 32 bits are zero. It also verifies that a forged API map
using the fixture's real PE identity and RVAs cannot redirect an export.
The host avoids calling the wrapper, game APIs, and managed code. Native discovery
and CoreCLR stay inactive. Before unloading, it restores its four IAT slots.

Results are `forwarding-results.json` and `enabled-results.json` in the corresponding
build directories. Both runners verify original and staged DLL hashes remain equal.
Passing these tests establishes these native behaviors; it does not replace an actual
in-game initialization test or establish an antivirus verdict.
