using System.Runtime.InteropServices;
using System.Text.Json;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using Il2CppInterop.Runtime;

namespace CarX.LoaderVerification;

[BepInPlugin("carx.loader.verification", "CarX Loader Verification", "1.0.0")]
public sealed class VerificationPlugin : BasePlugin
{
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate IntPtr DomainGetter();

    [DllImport("GameAssembly", EntryPoint = "il2cpp_domain_get", CallingConvention = CallingConvention.Cdecl)]
    private static extern IntPtr GetDomainPInvoke();

    public override void Load()
    {
        var gameAssembly = NativeLibrary.Load("GameAssembly.dll");
        var canonicalAddress = NativeLibrary.GetExport(gameAssembly, "il2cpp_domain_get");
        var nativeDomain = Marshal.GetDelegateForFunctionPointer<DomainGetter>(canonicalAddress)();
        var pinvokeDomain = GetDomainPInvoke();
        var interopDomain = IL2CPP.il2cpp_domain_get();
        if (nativeDomain == IntPtr.Zero || nativeDomain != pinvokeDomain || nativeDomain != interopDomain)
            throw new InvalidOperationException("BepInEx verification failed: canonical IL2CPP domain lookups disagree or returned null.");

        var proof = new
        {
            BasePluginLoaded = true,
            processId = Environment.ProcessId,
            processPath = Environment.ProcessPath,
            timeUtc = DateTimeOffset.UtcNow,
            domainGetCanonicalExport = $"0x{canonicalAddress:X}",
            domainGetCanonicalNativeLibrary = $"0x{nativeDomain:X}",
            domainGetCanonicalPInvoke = $"0x{pinvokeDomain:X}",
            domainGetIl2CppInteropRuntime = $"0x{interopDomain:X}",
            nativeLibraryAndPInvokeAgree = true,
            nativeLibraryAndIl2CppInteropAgree = true,
            runtime = RuntimeInformation.FrameworkDescription,
            interopRuntimeAssembly = typeof(IL2CPP).Assembly.FullName
        };
        Directory.CreateDirectory(Paths.BepInExRootPath);
        var path = Path.Combine(Paths.BepInExRootPath, "verification-plugin.json");
        var temporary = path + ".partial";
        File.WriteAllText(temporary, JsonSerializer.Serialize(proof, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(temporary, path, overwrite: true);
        Log.LogInfo($"CARX_BEPINEX_VERIFICATION_PLUGIN_LOADED PID={Environment.ProcessId}; canonical IL2CPP NativeLibrary, P/Invoke and Il2CppInterop domain lookups agree.");

        if (Environment.GetEnvironmentVariable("BEPINEX_VERIFY_EXIT") == "1")
        {
            // Let the chainloader finish startup before ending an explicit test.
            _ = Task.Run(async () =>
            {
                await Task.Delay(TimeSpan.FromSeconds(3)).ConfigureAwait(false);
                Environment.Exit(0);
            });
        }
    }
}
