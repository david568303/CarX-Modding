using System.Reflection;
using System.Diagnostics;
using System.Text.RegularExpressions;

namespace Doorstop;

public static class Entrypoint
{
    public static void Start()
    {
        string? logPath = null;
        try
        {
            var context = BepInEx.MetadataBootstrap.BootstrapContext.FromEnvironment();
            logPath = Path.Combine(context.BepInExRoot, "metadata-bootstrap.log");
            var productVersion = FileVersionInfo.GetVersionInfo(context.UnityPlayerPath).ProductVersion ?? "";
            var match = Regex.Match(productVersion, @"^(\d+)\.(\d+)\.(\d+)");
            if (!match.Success)
                throw new InvalidDataException("UnityPlayer has no recognized Unity version.");
            BepInEx.MetadataBootstrap.UnityBaseLibraries.Prepare(context, logPath, Version.Parse(match.Value));
            BepInEx.MetadataBootstrap.Bootstrap.Log(logPath, "Preparing metadata before BepInEx startup.");
            BepInEx.MetadataBootstrap.Bootstrap.Prepare(context, logPath);

            // BepInEx reads these variables inside its own Start(). Use its real
            // assembly path so its normal path discovery remains authoritative.
            var assemblyPath = Path.Combine(context.CoreDirectory, "BepInEx.Unity.IL2CPP.dll");
            if (!File.Exists(assemblyPath))
                throw new FileNotFoundException("The BepInEx IL2CPP preloader is missing.", assemblyPath);
            Environment.SetEnvironmentVariable("DOORSTOP_INVOKE_DLL_PATH", assemblyPath);
            var assembly = Assembly.LoadFrom(assemblyPath);
            var method = assembly.GetType("Doorstop.Entrypoint", throwOnError: true)!
                .GetMethod("Start", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static,
                    binder: null, types: Type.EmptyTypes, modifiers: null)
                ?? throw new MissingMethodException("BepInEx Doorstop.Entrypoint.Start was not found.");
            BepInEx.MetadataBootstrap.Bootstrap.Log(logPath, "Metadata ready; starting the BepInEx preloader.");
            method.Invoke(null, null);
        }
        catch (Exception error)
        {
            var actual = error is TargetInvocationException { InnerException: not null } invocation
                ? invocation.InnerException : error;
            var message = "BepInEx metadata preparation failed; the plugin loader was not started. " + actual;
            try
            {
                logPath ??= Path.Combine(Environment.CurrentDirectory, "metadata-bootstrap.log");
                BepInEx.MetadataBootstrap.Bootstrap.Log(logPath, message);
            }
            catch { /* An unavailable log location must not crash Unity. */ }
            try { Console.Error.WriteLine(message); } catch { }
        }
    }
}
