using System.Diagnostics;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

[assembly: InternalsVisibleTo("MetadataBootstrap.Tests")]

namespace BepInEx.MetadataBootstrap;

internal sealed record BootstrapContext(string GameDirectory, string CoreDirectory, string BepInExRoot,
    string GameAssemblyPath, string UnityPlayerPath, string OriginalMetadataPath, string ApiMapPath, string DecoderPath,
    string OutputPath, string ConfigPath)
{
    internal static BootstrapContext FromEnvironment()
    {
        var processPath = Environment.GetEnvironmentVariable("DOORSTOP_PROCESS_PATH");
        if (string.IsNullOrWhiteSpace(processPath))
            throw new InvalidOperationException("DOORSTOP_PROCESS_PATH was not supplied by Doorstop.");
        processPath = Path.GetFullPath(processPath);
        var gameDirectory = Path.GetDirectoryName(processPath)
            ?? throw new InvalidOperationException("The game executable has no containing directory.");
        var coreDirectory = Path.GetDirectoryName(typeof(BootstrapContext).Assembly.Location)
            ?? throw new InvalidOperationException("The metadata bootstrap has no assembly location.");
        var bepinRoot = Directory.GetParent(coreDirectory)?.FullName
            ?? throw new InvalidOperationException("The BepInEx core directory has no parent.");
        var dataDirectory = Path.Combine(gameDirectory, Path.GetFileNameWithoutExtension(processPath) + "_Data");
        if (!Directory.Exists(dataDirectory)) dataDirectory = Path.Combine(gameDirectory, "Data");
        var configuredGameAssembly = Environment.GetEnvironmentVariable("BEPINEX_GAME_ASSEMBLY_PATH");
        var gameAssembly = Path.GetFullPath(string.IsNullOrWhiteSpace(configuredGameAssembly)
            ? Path.Combine(gameDirectory, "GameAssembly.dll") : configuredGameAssembly, gameDirectory);
        return new(gameDirectory, coreDirectory, bepinRoot, gameAssembly,
            Path.Combine(gameDirectory, "UnityPlayer.dll"),
            Path.Combine(dataDirectory, "il2cpp_data", "Metadata", "global-metadata.dat"),
            Path.Combine(gameDirectory, "doorstop_api.ini"),
            Path.Combine(coreDirectory, "scripts", "normalize_metadata.py"),
            Path.Combine(bepinRoot, "cache", "metadata", "global-metadata.dat"),
            Path.Combine(bepinRoot, "config", "BepInEx.cfg"));
    }
}

internal sealed record InputFingerprint(int Format, string GameAssembly, string UnityPlayer,
    string Metadata, string ApiMap, string Decoder);
internal sealed record CacheFingerprint(InputFingerprint Inputs, string Output);

internal static class Bootstrap
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    internal static void Log(string path, string message)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.AppendAllText(path, $"[{DateTimeOffset.Now:O}] {message}{Environment.NewLine}", new UTF8Encoding(false));
    }

    internal static string HashFile(string path)
    {
        using var stream = File.OpenRead(path);
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(stream));
    }

    internal static InputFingerprint Fingerprint(BootstrapContext context) => new(2,
        HashFile(context.GameAssemblyPath), HashFile(context.UnityPlayerPath),
        HashFile(context.OriginalMetadataPath), HashFile(context.ApiMapPath), HashDecoderScripts(context.DecoderPath));

    private static string HashDecoderScripts(string decoderPath)
    {
        // Include sibling modules used by the normalizer, so updating native
        // inference code also invalidates an earlier normalized cache.
        var entries = Directory.EnumerateFiles(Path.GetDirectoryName(decoderPath)!, "*.py")
            .OrderBy(Path.GetFileName, StringComparer.Ordinal)
            .Select(path => Path.GetFileName(path) + "\0" + HashFile(path));
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", entries))));
    }

    internal static void Prepare(BootstrapContext context, string logPath,
        Action<BootstrapContext, string, string>? decode = null)
    {
        var fingerprint = Fingerprint(context);
        var descriptorPath = context.OutputPath + ".fingerprint.json";
        if (CacheIsValid(context.OutputPath, descriptorPath, fingerprint))
        {
            Log(logPath, "Validated the metadata cache against all input and output SHA-256 fingerprints.");
        }
        else
        {
            Directory.CreateDirectory(Path.GetDirectoryName(context.OutputPath)!);
            var temporaryOutput = context.OutputPath + "." + Guid.NewGuid().ToString("N") + ".partial";
            try
            {
                (decode ?? RunDecoder)(context, temporaryOutput, logPath);
                ValidateMetadata(temporaryOutput);
                // Never publish a cache produced while Steam or another process
                // was replacing an input file.
                if (fingerprint != Fingerprint(context))
                    throw new IOException("Game inputs changed during metadata preparation; run the game again after the update finishes.");
                var descriptor = new CacheFingerprint(fingerprint, HashFile(temporaryOutput));
                File.Move(temporaryOutput, context.OutputPath, overwrite: true);
                foreach (var suffix in new[] { ".evidence.json", ".json" })
                    if (File.Exists(temporaryOutput + suffix))
                        File.Move(temporaryOutput + suffix, context.OutputPath + suffix, overwrite: true);
                AtomicWrite(descriptorPath, JsonSerializer.Serialize(descriptor, JsonOptions) + "\n");
                Log(logPath, "Published a validated metadata cache and its input/output fingerprints.");
            }
            finally
            {
                if (File.Exists(temporaryOutput)) File.Delete(temporaryOutput);
                foreach (var suffix in new[] { ".evidence.json", ".json" })
                    if (File.Exists(temporaryOutput + suffix)) File.Delete(temporaryOutput + suffix);
            }
        }
        var replacement = Path.GetRelativePath(context.BepInExRoot, context.OutputPath).Replace('\\', '/');
        var value = "{BepInEx}/" + replacement;
        var original = File.Exists(context.ConfigPath) ? File.ReadAllText(context.ConfigPath) : "";
        var updated = UpdateMetadataConfig(original, value);
        if (original != updated) AtomicWrite(context.ConfigPath, updated);
        Log(logPath, "Configured IL2CPP.GlobalMetadataPath for the validated cache.");
    }

    internal static bool CacheIsValid(string output, string descriptorPath, InputFingerprint expected)
    {
        if (!File.Exists(output) || !File.Exists(descriptorPath)) return false;
        try
        {
            var descriptor = JsonSerializer.Deserialize<CacheFingerprint>(File.ReadAllText(descriptorPath));
            if (descriptor?.Inputs != expected || descriptor.Output != HashFile(output)) return false;
            ValidateMetadata(output);
            return true;
        }
        catch (Exception error) when (error is IOException or JsonException or InvalidDataException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    internal static void ValidateMetadata(string path)
    {
        using var stream = File.OpenRead(path);
        using var reader = new BinaryReader(stream);
        if (stream.Length < 20 || reader.ReadUInt32() != 0xFAB11BAF)
            throw new InvalidDataException("The decoder did not produce standard IL2CPP metadata.");
        var version = reader.ReadInt32();
        if (version < 16 || version > 10000)
            throw new InvalidDataException("The decoded metadata version is invalid.");
        var firstOffset = reader.ReadInt32();
        var firstSize = reader.ReadInt32();
        if (firstOffset < 20 || firstOffset > stream.Length || firstSize < 0
            || (long)firstOffset + firstSize > stream.Length)
            throw new InvalidDataException("The decoded metadata's first section is outside its file.");
        if (version >= 38)
        {
            var count = reader.ReadInt32();
            if (count < 0 || count > firstSize)
                throw new InvalidDataException("The decoded metadata's first section count is invalid.");
        }
    }

    internal static void RunDecoder(BootstrapContext context, string temporaryOutput, string logPath)
    {
        var configured = Environment.GetEnvironmentVariable("BEPINEX_METADATA_PYTHON");
        var bundled = Path.Combine(context.BepInExRoot, "compatibility", "python", "python.exe");
        var executable = !string.IsNullOrWhiteSpace(configured) ? configured
            : File.Exists(bundled) ? bundled : "python.exe";
        var candidates = new[] { executable };
        var failures = new List<string>();
        foreach (var candidate in candidates)
        {
            var start = new ProcessStartInfo(candidate)
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = context.GameDirectory,
            };
            start.ArgumentList.Add("-B");
            start.ArgumentList.Add(context.DecoderPath);
            start.ArgumentList.Add("--game"); start.ArgumentList.Add(context.GameAssemblyPath);
            start.ArgumentList.Add("--metadata"); start.ArgumentList.Add(context.OriginalMetadataPath);
            start.ArgumentList.Add("--api-map"); start.ArgumentList.Add(context.ApiMapPath);
            start.ArgumentList.Add("--output"); start.ArgumentList.Add(temporaryOutput);
            Process? process;
            try { process = Process.Start(start); }
            catch (System.ComponentModel.Win32Exception error)
            {
                failures.Add(candidate + ": " + error.Message);
                continue;
            }
            if (process is null) throw new InvalidOperationException("The metadata decoder process did not start.");
            using (process)
            {
                var stdout = process.StandardOutput.ReadToEndAsync();
                var stderr = process.StandardError.ReadToEndAsync();
                if (!process.WaitForExit(120 * 1000))
                {
                    try { process.Kill(entireProcessTree: true); } catch { }
                    throw new TimeoutException("Metadata decoding exceeded two minutes.");
                }
                var output = stdout.GetAwaiter().GetResult();
                var errors = stderr.GetAwaiter().GetResult();
                if (output.Length > 0) Log(logPath, output.TrimEnd());
                if (errors.Length > 0) Log(logPath, errors.TrimEnd());
                if (process.ExitCode != 0)
                    throw new InvalidDataException($"The metadata decoder exited with code {process.ExitCode}; see metadata-bootstrap.log.");
                return;
            }
        }
        throw new FileNotFoundException("Python 3 could not be started. BEPINEX_METADATA_PYTHON can select its executable. " + string.Join("; ", failures));
    }

    internal static string UpdateMetadataConfig(string content, string value)
    {
        var newline = content.Contains("\r\n", StringComparison.Ordinal) ? "\r\n" : "\n";
        var lines = Regex.Split(content, "(?<=\\n)").Where(line => line.Length > 0).ToList();
        var result = new StringBuilder();
        var inSection = false;
        var foundSection = false;
        var foundKeyInSection = false;
        void EnsureNewline()
        {
            if (result.Length > 0 && result[^1] != '\n') result.Append(newline);
        }
        void InsertKey()
        {
            EnsureNewline();
            result.Append("GlobalMetadataPath = ").Append(value).Append(newline);
        }
        foreach (var line in lines)
        {
            var body = line.TrimEnd('\r', '\n');
            var trimmed = body.Trim();
            var end = line[body.Length..];
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                if (inSection && !foundKeyInSection) InsertKey();
                inSection = trimmed == "[IL2CPP]";
                foundSection |= inSection;
                foundKeyInSection = false;
            }
            var equals = body.IndexOf('=');
            if (inSection && equals >= 0 && body[..equals].Trim() == "GlobalMetadataPath")
            {
                result.Append(body[..(equals + 1)]).Append(' ').Append(value).Append(end);
                foundKeyInSection = true;
            }
            else result.Append(line);
        }
        if (inSection && !foundKeyInSection) InsertKey();
        if (!foundSection)
        {
            EnsureNewline();
            if (result.Length > 0) result.Append(newline);
            result.Append("[IL2CPP]").Append(newline);
            InsertKey();
        }
        return result.ToString();
    }

    internal static void AtomicWrite(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".partial";
        try
        {
            File.WriteAllText(temporary, text, new UTF8Encoding(false));
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
