using System.IO.Compression;
using System.Net;
using System.Reflection.PortableExecutable;
using System.Reflection.Metadata;
using System.Text.Json;

namespace BepInEx.MetadataBootstrap;

internal static class UnityBaseLibraries
{
    internal const string DefaultSource = "https://unity.bepinex.dev/libraries/{VERSION}.zip";
    private const int MaximumArchiveBytes = 64 * 1024 * 1024;
    private sealed record Selection(int Format, string Target, string Version, string Archive,
        string Sha256, string OriginalSource, string? PreviousArchive = null);

    internal static void Prepare(BootstrapContext context, string logPath, Version version,
        Func<Uri, byte[]?>? fetch = null)
    {
        var directory = Path.Combine(context.BepInExRoot, "unity-libs");
        var statePath = Path.Combine(directory, ".carx-base-libraries.json");
        var config = File.Exists(context.ConfigPath) ? File.ReadAllText(context.ConfigPath) : "";
        var configured = ReadSetting(config, "UnityBaseLibrariesSource");
        var interopBase = ReadSetting(config, "IL2CPPInteropAssembliesPath");
        if (interopBase != null && interopBase != "{BepInEx}" ||
            Environment.GetCommandLineArgs().Contains("--unhollowed-path"))
            return;
        var previous = ReadSelection(statePath);
        var managed = previous?.Format == 1 && (configured == previous.Archive ||
            configured != null && configured == previous.PreviousArchive) &&
            previous.OriginalSource == DefaultSource;
        if (configured != null && configured != DefaultSource && !managed)
            return;

        Directory.CreateDirectory(directory);
        var target = new Version(version.Major, version.Minor, version.Build);
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
        fetch ??= uri => Download(client, uri);
        var deadline = DateTime.UtcNow.AddSeconds(45);
        string? selectedPath = null;
        Version? selectedVersion = null;
        Exception? downloadError = null;
        for (var patch = target.Build; patch >= Math.Max(0, target.Build - 63); patch--)
        {
            var candidate = new Version(target.Major, target.Minor, patch);
            var path = Path.Combine(directory, candidate + ".zip");
            if (TryValidate(path))
            {
                selectedPath = path;
                selectedVersion = candidate;
                break;
            }

            if (DateTime.UtcNow >= deadline) break;
            try
            {
                var bytes = fetch(new Uri(DefaultSource.Replace("{VERSION}", candidate.ToString())));
                if (bytes == null) continue;
                Validate(bytes);
                WriteArchive(path, bytes);
                selectedPath = path;
                selectedVersion = candidate;
                break;
            }
            catch (Exception error) when (error is HttpRequestException or IOException or InvalidDataException or
                OperationCanceledException or BadImageFormatException)
            {
                downloadError = error;
                Bootstrap.Log(logPath, $"Could not obtain validated Unity libraries {candidate}: {error.Message}");
                // An unavailable service should not cause dozens of timed-out requests.
                break;
            }
        }

        if (selectedPath == null)
        {
            foreach (var path in Directory.EnumerateFiles(directory, "*.zip")
                .Select(path => (Path: path, Version: ParseArchiveVersion(path)))
                .Where(item => item.Version != null && item.Version.Major == target.Major &&
                    item.Version.Minor == target.Minor && item.Version <= target)
                .OrderByDescending(item => item.Version))
            {
                if (!TryValidate(path.Path)) continue;
                selectedPath = path.Path;
                selectedVersion = path.Version;
                break;
            }
        }

        if (selectedPath == null)
            throw new IOException($"No validated Unity base libraries are available for {target} or an earlier patch in the same Unity branch. Existing interop files were preserved.", downloadError);

        var archive = Path.GetFileName(selectedPath);
        var selection = new Selection(1, target.ToString(), selectedVersion!.ToString(), archive,
            Bootstrap.HashFile(selectedPath), DefaultSource, managed ? configured : null);
        var interopDirectory = Path.Combine(context.BepInExRoot, "interop");
        if (previous?.Version != selection.Version || previous.Sha256 != selection.Sha256 ||
            !File.Exists(Path.Combine(interopDirectory, "UnityEngine.CoreModule.dll")))
        {
            // Upstream hashes extracted DLLs, not the selected archive or source setting.
            // Invalidate its marker so a newly available exact pack is actually used.
            var hashPath = Path.Combine(interopDirectory, "assembly-hash.txt");
            if (File.Exists(hashPath)) File.Delete(hashPath);
        }
        // Publish ownership first so interrupted configuration writes can be retried.
        Bootstrap.AtomicWrite(statePath, JsonSerializer.Serialize(selection) + "\n");
        var updated = Bootstrap.UpdateConfigSetting(config, "UnityBaseLibrariesSource", archive);
        if (config != updated) Bootstrap.AtomicWrite(context.ConfigPath, updated);
        Bootstrap.Log(logPath, selectedVersion == target
            ? $"Validated exact Unity base libraries {selectedVersion}."
            : $"Unity base libraries {target} are unavailable; selected {selectedVersion} from the same Unity branch for interop unstripping. The exact version will be checked again at the next startup.");
    }

    private static string? ReadSetting(string config, string key)
    {
        var inSection = false;
        string? value = null;
        foreach (var raw in config.Split('\n'))
        {
            var line = raw.Trim();
            if (line.StartsWith('[') && line.EndsWith(']')) inSection = line == "[IL2CPP]";
            if (!inSection) continue;
            var equals = line.IndexOf('=');
            if (equals >= 0 && line[..equals].Trim() == key)
                value = line[(equals + 1)..].Trim();
        }
        return value;
    }

    private static Selection? ReadSelection(string path)
    {
        try { return File.Exists(path) ? JsonSerializer.Deserialize<Selection>(File.ReadAllText(path)) : null; }
        catch (Exception error) when (error is IOException or JsonException) { return null; }
    }

    private static Version? ParseArchiveVersion(string path) =>
        Version.TryParse(Path.GetFileNameWithoutExtension(path), out var version) && version.Revision == -1 &&
        version.Build >= 0 ? version : null;

    private static byte[]? Download(HttpClient client, Uri uri)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        using var response = client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, timeout.Token).GetAwaiter().GetResult();
        if (response.StatusCode == HttpStatusCode.NotFound) return null;
        response.EnsureSuccessStatusCode();
        if (response.Content.Headers.ContentLength > MaximumArchiveBytes)
            throw new InvalidDataException("Unity library archive exceeds the download limit.");
        using var input = response.Content.ReadAsStreamAsync(timeout.Token).GetAwaiter().GetResult();
        using var output = new MemoryStream();
        var buffer = new byte[81920];
        int read;
        while ((read = input.ReadAsync(buffer.AsMemory(), timeout.Token).GetAwaiter().GetResult()) != 0)
        {
            if (output.Length + read > MaximumArchiveBytes)
                throw new InvalidDataException("Unity library archive exceeds the download limit.");
            output.Write(buffer, 0, read);
        }
        return output.ToArray();
    }

    private static bool TryValidate(string path)
    {
        try
        {
            if (!File.Exists(path) || new FileInfo(path).Length > MaximumArchiveBytes) return false;
            Validate(File.ReadAllBytes(path));
            return true;
        }
        catch (Exception error) when (error is IOException or InvalidDataException or BadImageFormatException) { return false; }
    }

    private static void Validate(byte[] bytes)
    {
        if (bytes.Length > MaximumArchiveBytes) throw new InvalidDataException("Unity library archive is too large.");
        using var input = new MemoryStream(bytes, writable: false);
        using var zip = new ZipArchive(input, ZipArchiveMode.Read);
        if (zip.Entries.Count == 0 || zip.Entries.Count > 512)
            throw new InvalidDataException("Unexpected number of Unity library files.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var entry in zip.Entries)
        {
            var name = entry.FullName;
            total += entry.Length;
            if (name.IndexOfAny(new[] { '/', '\\', ':' }) >= 0 || !name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) ||
                !names.Add(name) || entry.Length > MaximumArchiveBytes || total > 256L * 1024 * 1024)
                throw new InvalidDataException("Unity library archive contains an unexpected file.");
            using var source = entry.Open();
            using var assembly = new MemoryStream();
            source.CopyTo(assembly);
            assembly.Position = 0;
            using var pe = new PEReader(assembly);
            if (!pe.HasMetadata || pe.PEHeaders.CorHeader == null)
                throw new InvalidDataException($"Unity library {name} is not a managed assembly.");
            var metadata = pe.GetMetadataReader();
            if (!metadata.IsAssembly || string.IsNullOrEmpty(metadata.GetString(metadata.GetAssemblyDefinition().Name)))
                throw new InvalidDataException($"Unity library {name} has no valid assembly definition.");
        }
        if (!names.Contains("UnityEngine.CoreModule.dll") || !names.Contains("UnityEngine.dll"))
            throw new InvalidDataException("Unity library archive is missing its core assemblies.");
    }

    private static void WriteArchive(string path, byte[] bytes)
    {
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".partial";
        try
        {
            File.WriteAllBytes(temporary, bytes);
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
