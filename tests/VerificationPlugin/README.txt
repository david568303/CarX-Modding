This is an actual BepInEx IL2CPP BasePlugin used for loader verification.

Build with the existing SDK:

    dotnet build tests/VerificationPlugin/VerificationPlugin.csproj -c Release

The assembly is written under .work/build/VerificationPlugin by the repository
Directory.Build.props. Copy only CarX.BepInEx.Verification.dll into the test
package's BepInEx/plugins directory. It writes BepInEx/verification-plugin.json
only after NativeLibrary, direct P/Invoke and Il2CppInterop.Runtime agree on a
nonzero IL2CPP domain. Its unique log marker is
CARX_BEPINEX_VERIFICATION_PLUGIN_LOADED.

Normal execution does not exit the game. Setting BEPINEX_VERIFY_EXIT=1 explicitly
requests a clean process exit three seconds after plugin Load completes.
