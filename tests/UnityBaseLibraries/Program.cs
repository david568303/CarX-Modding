using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using BepInEx.MetadataBootstrap;

var root = Path.Combine(Path.GetTempPath(), "CarX base library tests " + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
var passed = 0;
var fixtureAssembly = File.ReadAllBytes(Assembly.GetExecutingAssembly().Location);

void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
}

void Test(string name, Action test)
{
    test();
    passed++;
    Console.WriteLine("PASS " + name);
}

BootstrapContext Context(string name, string? config = null)
{
    var game = Path.Combine(root, name);
    var bepin = Path.Combine(game, "BepInEx");
    var core = Path.Combine(bepin, "core");
    var configPath = Path.Combine(bepin, "config", "BepInEx.cfg");
    Directory.CreateDirectory(core);
    if (config != null)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(configPath)!);
        File.WriteAllText(configPath, config);
    }
    return new BootstrapContext(game, core, bepin, Path.Combine(game, "GameAssembly.dll"),
        Path.Combine(game, "UnityPlayer.dll"), Path.Combine(game, "original-metadata.dat"),
        Path.Combine(game, "doorstop_api.ini"), Path.Combine(core, "bootstrap.dll"),
        Path.Combine(bepin, "cache", "metadata", "global-metadata.dat"), configPath);
}

string LogPath(BootstrapContext context) => Path.Combine(context.BepInExRoot, "test.log");
string LibPath(BootstrapContext context, string name) => Path.Combine(context.BepInExRoot, "unity-libs", name);

byte[] Archive(params (string Name, byte[] Bytes)[] entries)
{
    using var bytes = new MemoryStream();
    using (var archive = new ZipArchive(bytes, ZipArchiveMode.Create, leaveOpen: true))
    {
        foreach (var entry in entries)
        {
            using var stream = archive.CreateEntry(entry.Name).Open();
            stream.Write(entry.Bytes);
        }
    }
    return bytes.ToArray();
}

byte[] ValidArchive() => Archive(("UnityEngine.CoreModule.dll", fixtureAssembly), ("UnityEngine.dll", fixtureAssembly));

string ReadSource(BootstrapContext context)
{
    var inSection = false;
    foreach (var line in File.ReadAllLines(context.ConfigPath))
    {
        var text = line.Trim();
        if (text.StartsWith('[')) inSection = text == "[IL2CPP]";
        if (inSection && text.StartsWith("UnityBaseLibrariesSource", StringComparison.Ordinal))
            return text[(text.IndexOf('=') + 1)..].Trim();
    }
    return "";
}

void Cached(BootstrapContext context, string name, byte[]? content = null)
{
    Directory.CreateDirectory(Path.GetDirectoryName(LibPath(context, name))!);
    File.WriteAllBytes(LibPath(context, name), content ?? ValidArchive());
}

try
{
    Test("exact archive is preferred and config retains unrelated settings", () =>
    {
        const string config = "[Other]\r\nKeep = yes\r\n\r\n[IL2CPP]\r\nUpdateInteropAssemblies = true\r\n";
        var context = Context("exact", config);
        var requests = new List<string>();
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
        {
            requests.Add(uri.AbsoluteUri);
            return ValidArchive();
        });
        Check(requests.Count == 1 && requests[0].EndsWith("/6000.3.28.zip", StringComparison.Ordinal), "Exact download was not first.");
        Check(ReadSource(context) == "6000.3.28.zip", "Selected exact filename was not configured.");
        Check(File.ReadAllText(context.ConfigPath).Contains("Keep = yes\r\n"), "Unrelated configuration changed.");
        Check(File.Exists(LibPath(context, "6000.3.28.zip")), "Exact ZIP was not cached.");
    });

    Test("missing exact archive chooses closest previous patch", () =>
    {
        var context = Context("fallback");
        var requests = new List<string>();
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
        {
            requests.Add(Path.GetFileName(uri.AbsolutePath));
            return uri.AbsolutePath.EndsWith("6000.3.26.zip", StringComparison.Ordinal) ? ValidArchive() : null;
        });
        Check(requests.SequenceEqual(new[] { "6000.3.28.zip", "6000.3.27.zip", "6000.3.26.zip" }), "Fallback order crossed or skipped a patch.");
        Check(ReadSource(context) == "6000.3.26.zip", "Fallback archive was disguised as the target version.");
        Check(!File.Exists(LibPath(context, "6000.3.28.zip")), "A missing exact version was cached as successful.");
    });

    Test("managed fallback automatically retries exact libraries next launch", () =>
    {
        var context = Context("retry-exact");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
            uri.AbsolutePath.EndsWith("6000.3.27.zip", StringComparison.Ordinal) ? ValidArchive() : null);
        Check(ReadSource(context) == "6000.3.27.zip", "Initial fallback was not selected.");
        var requestedExact = false;
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
        {
            requestedExact = uri.AbsolutePath.EndsWith("6000.3.28.zip", StringComparison.Ordinal);
            return ValidArchive();
        });
        Check(requestedExact && ReadSource(context) == "6000.3.28.zip", "The managed fallback pinned future launches.");
    });

    Test("upgrading from fallback libraries invalidates the interop marker", () =>
    {
        var context = Context("upgrade-marker");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
            uri.AbsolutePath.EndsWith("6000.3.27.zip", StringComparison.Ordinal) ? ValidArchive() : null);
        var interop = Path.Combine(context.BepInExRoot, "interop");
        Directory.CreateDirectory(interop);
        File.WriteAllBytes(Path.Combine(interop, "UnityEngine.CoreModule.dll"), fixtureAssembly);
        var marker = Path.Combine(interop, "assembly-hash.txt");
        File.WriteAllText(marker, "previous fallback generation");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ => ValidArchive());
        Check(ReadSource(context) == "6000.3.28.zip", "Exact archive was not selected after becoming available.");
        Check(!File.Exists(marker), "New exact libraries left the fallback interop hash valid.");
        Check(File.Exists(Path.Combine(interop, "UnityEngine.CoreModule.dll")), "Marker invalidation removed existing interop assemblies.");
    });

    Test("an interrupted source update recovers its previous managed archive", () =>
    {
        var context = Context("interrupted-upgrade");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), uri =>
            uri.AbsolutePath.EndsWith("6000.3.27.zip", StringComparison.Ordinal) ? ValidArchive() : null);
        var statePath = LibPath(context, ".carx-base-libraries.json");
        var state = JsonNode.Parse(File.ReadAllText(statePath))!.AsObject();
        state["Archive"] = "6000.3.28.zip";
        state["Version"] = "6000.3.28";
        state["PreviousArchive"] = "6000.3.27.zip";
        File.WriteAllText(statePath, state.ToJsonString());
        Cached(context, "6000.3.28.zip");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            throw new Exception("The validated exact archive was downloaded again."));
        Check(ReadSource(context) == "6000.3.28.zip", "Interrupted source publication stopped managing the prior owned selection.");
    });

    Test("unchanged libraries preserve a complete interop marker", () =>
    {
        var context = Context("unchanged-marker");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ => ValidArchive());
        var interop = Path.Combine(context.BepInExRoot, "interop");
        Directory.CreateDirectory(interop);
        File.WriteAllBytes(Path.Combine(interop, "UnityEngine.CoreModule.dll"), fixtureAssembly);
        var marker = Path.Combine(interop, "assembly-hash.txt");
        File.WriteAllText(marker, "valid unchanged generation");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            throw new Exception("Validated exact cache was downloaded again."));
        Check(File.ReadAllText(marker) == "valid unchanged generation", "Unchanged validated libraries forced needless regeneration.");
    });

    Test("missing CoreModule invalidates an otherwise unchanged interop marker", () =>
    {
        var context = Context("incomplete-marker");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ => ValidArchive());
        var interop = Path.Combine(context.BepInExRoot, "interop");
        Directory.CreateDirectory(interop);
        var marker = Path.Combine(interop, "assembly-hash.txt");
        File.WriteAllText(marker, "incomplete generation");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            throw new Exception("Validated exact cache was downloaded again."));
        Check(!File.Exists(marker), "Missing CoreModule left an incomplete interop cache marked valid.");
    });

    Test("explicit user sources and offline mode remain authoritative", () =>
    {
        foreach (var source in new[] { "", "custom.zip", "https://example.invalid/{VERSION}.zip" })
        {
            var original = "[IL2CPP]\nUnityBaseLibrariesSource = " + source + "\n";
            var context = Context("custom-" + Guid.NewGuid().ToString("N"), original);
            var downloads = 0;
            UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            {
                downloads++;
                throw new Exception("Custom source was fetched.");
            });
            Check(downloads == 0 && File.ReadAllText(context.ConfigPath) == original, "Explicit user source was changed.");
        }
    });

    Test("a user source change after managed selection stays authoritative", () =>
    {
        var context = Context("custom-after-fallback");
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ => ValidArchive());
        const string customConfig = "[IL2CPP]\nUnityBaseLibrariesSource = user-provided.zip\n";
        File.WriteAllText(context.ConfigPath, customConfig);
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 29), _ =>
            throw new Exception("User override was fetched."));
        Check(File.ReadAllText(context.ConfigPath) == customConfig, "Managed state replaced a subsequent user source change.");
    });

    Test("nondefault interop locations are left to the configured loader", () =>
    {
        const string original = "[IL2CPP]\nIL2CPPInteropAssembliesPath = {BepInEx}/custom\n" +
            "UnityBaseLibrariesSource = https://unity.bepinex.dev/libraries/{VERSION}.zip\n";
        var context = Context("custom-interop-path", original);
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            throw new Exception("A custom interop location was managed."));
        Check(File.ReadAllText(context.ConfigPath) == original, "Custom interop configuration changed.");
        Check(!Directory.Exists(Path.Combine(context.BepInExRoot, "unity-libs")), "Default library cache was created for a custom interop location.");
    });

    Test("network failure uses only a compatible validated cached archive", () =>
    {
        var context = Context("offline-cache");
        Cached(context, "6000.3.19.zip");
        Cached(context, "6000.2.99.zip");
        Cached(context, "6000.3.29.zip");
        Cached(context, "6000.3.27.zip", Encoding.UTF8.GetBytes("not a zip"));
        UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ =>
            throw new HttpRequestException("offline"));
        Check(ReadSource(context) == "6000.3.19.zip", "Offline fallback accepted another branch, a future version or corrupt content.");
    });

    Test("unavailable dependencies preserve configuration and previous generated assemblies", () =>
    {
        const string config = "[IL2CPP]\nUnityBaseLibrariesSource = https://unity.bepinex.dev/libraries/{VERSION}.zip\n";
        var context = Context("failure-preserves", config);
        var interop = Path.Combine(context.BepInExRoot, "interop", "UnityEngine.CoreModule.dll");
        Directory.CreateDirectory(Path.GetDirectoryName(interop)!);
        File.WriteAllText(interop, "old generated assembly sentinel");
        var failed = false;
        try
        {
            UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 28), _ => null);
        }
        catch (IOException) { failed = true; }
        Check(failed, "Missing base libraries did not stop before invoking the destructive preloader.");
        Check(File.ReadAllText(context.ConfigPath) == config, "Failed resolution changed the user's source.");
        Check(File.ReadAllText(interop) == "old generated assembly sentinel", "Failed resolution removed existing interop.");
    });

    Test("unsafe or invalid archive payloads are rejected", () =>
    {
        var invalidArchives = new[]
        {
            Encoding.UTF8.GetBytes("not a zip"),
            Archive(("UnityEngine.CoreModule.dll", Encoding.UTF8.GetBytes("not a PE")), ("UnityEngine.dll", fixtureAssembly)),
            Archive(("UnityEngine.dll", fixtureAssembly)),
            Archive(("../UnityEngine.CoreModule.dll", fixtureAssembly), ("UnityEngine.dll", fixtureAssembly)),
            Archive(("UnityEngine.CoreModule.dll", fixtureAssembly), ("UnityEngine.dll", fixtureAssembly), ("unityengine.DLL", fixtureAssembly)),
            Archive(("UnityEngine.CoreModule.dll", fixtureAssembly), ("UnityEngine.dll", fixtureAssembly), ("payload.exe", fixtureAssembly)),
        };
        foreach (var invalidArchive in invalidArchives)
        {
            var context = Context("invalid-" + Guid.NewGuid().ToString("N"));
            var failed = false;
            try
            {
                UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 0), _ => invalidArchive);
            }
            catch (IOException) { failed = true; }
            Check(failed, "Malformed payload was accepted.");
            Check(!File.Exists(context.ConfigPath), "Rejected archive changed the active configuration.");
        }
    });

    Test("version search never crosses the Unity major-minor branch", () =>
    {
        var context = Context("zero-patch");
        var requests = new List<string>();
        try
        {
            UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 4, 0), uri =>
            {
                requests.Add(Path.GetFileName(uri.AbsolutePath));
                return null;
            });
        }
        catch (IOException) { }
        Check(requests.SequenceEqual(new[] { "6000.4.0.zip" }), "Search crossed into another Unity branch.");
    });

    Test("missing archives have a bounded probe count", () =>
    {
        var context = Context("bounded-probes");
        var requests = 0;
        try
        {
            UnityBaseLibraries.Prepare(context, LogPath(context), new Version(6000, 3, 200), _ =>
            {
                requests++;
                return null;
            });
        }
        catch (IOException) { }
        Check(requests > 0 && requests <= 65, "Missing archive search is unbounded.");
    });

    Console.WriteLine($"Passed {passed} base library tests.");
}
finally
{
    Directory.Delete(root, recursive: true);
}
