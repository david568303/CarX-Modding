using System.Buffers.Binary;
using BepInEx.MetadataBootstrap;

var passed = 0;
void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
void Test(string name, Action test) { test(); Console.WriteLine("PASS " + name); passed++; }
byte[] ValidMetadata()
{
    var bytes = new byte[32];
    BinaryPrimitives.WriteUInt32LittleEndian(bytes, 0xFAB11BAF);
    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(4), 39);
    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(8), 20);
    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(12), 12);
    BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(16), 3);
    return bytes;
}

byte[] StandardMetadata(int version)
{
    int[] sizes =
    {
        8, 2, 8, 21, 20, version == 38 ? 27 : 24, version == 38 ? 9 : 6,
        9, 1, 9, 9, 9, 13, 1, 16, 4, 1, 4, 5, 72, 34, 68, 5, 4, 1, 8, 1, 8, 5, 2, 4,
    };
    var offsets = new int[sizes.Length];
    var at = MetadataNormalizer.HeaderSize;
    for (var i = 0; i < sizes.Length; i++)
    {
        var alignment = i == 8 ? 8 : 4;
        at += (-at) & (alignment - 1);
        offsets[i] = at;
        at += sizes[i];
    }
    var bytes = new byte[at];
    Put(bytes, 0, MetadataNormalizer.Magic);
    Put(bytes, 4, (uint)version);
    for (var i = 0; i < sizes.Length; i++)
    {
        at = offsets[i];
        Put(bytes, 8 + i * 12, (uint)at);
        Put(bytes, 12 + i * 12, (uint)sizes[i]);
        Put(bytes, 16 + i * 12, i == 0 ? 2u : 1u);
        switch (i)
        {
            case 0: Put(bytes, at + 4, 2); break;
            case 2: bytes[at + 1] = (byte)'A'; break;
            case 4: Put(bytes, at + 16, 0x17000001); break;
            case 5: Put(bytes, at + (version == 38 ? 15 : 12), 0x06000001); break;
            case 11: Put(bytes, at + 5, 0x04000001); break;
            case 19:
                for (var member = 0; member < 8; member++) bytes[at + 48 + member * 2] = 1;
                break;
            case 20:
                Put(bytes, at + 9, 1);
                Put(bytes, at + 14, 1);
                break;
            case 21: Put(bytes, at + 4, 0x20000001); break;
            case 27: Put(bytes, at + 4, 1); break;
        }
    }
    return bytes;
}

void Put(byte[] bytes, int offset, uint value) => BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(offset), value);
int Word(byte[] bytes, int offset) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(offset));

(byte[] Encoded, NativeDecoder Decoder) Obfuscate(byte[] standard)
{
    const int headerLength = 31 * 12;
    const int headerKey = 213;
    const int claimedOffsetDelta = 64;
    const int sectionKeyAddend = 37;
    int[] encrypted = { 0, 1, 2, 4, 5, 11, 21 };
    var shift = headerLength - MetadataNormalizer.HeaderSize;
    var encoded = new byte[standard.Length + shift + 128];
    var sections = new List<NativeSection>();
    for (var i = 0; i < 31; i++)
    {
        var clearOffset = Word(standard, 8 + i * 12);
        var size = Word(standard, 12 + i * 12);
        var count = Word(standard, 16 + i * 12);
        var slot = (i * 7 + 3) % 31 * 12;
        var rawOffset = clearOffset + shift;
        Put(encoded, slot, (uint)count);
        Put(encoded, slot + 4, (uint)(rawOffset + claimedOffsetDelta));
        Put(encoded, slot + 8, (uint)size);
        standard.AsSpan(clearOffset, size).CopyTo(encoded.AsSpan(rawOffset));
        if (!encrypted.Contains(i)) continue;
        for (var j = 0; j < size; j++) encoded[rawOffset + j] ^= (byte)(size + sectionKeyAddend + j);
        sections.Add(new NativeSection(slot + 8, slot + 4, -claimedOffsetDelta, 1, sectionKeyAddend, 0, 0, 0));
    }
    for (var i = 0; i < headerLength; i++) encoded[i] ^= (byte)(headerKey + i);
    return (encoded, new NativeDecoder(new NativeHeader(headerLength, headerKey, 0), sections.ToArray(), 0, 0, 0));
}

var temporary = Path.Combine(Path.GetTempPath(), "Metadata bootstrap tests " + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temporary);
BootstrapContext Context(string name)
{
    var game = Path.Combine(temporary, name);
    var bepin = Path.Combine(game, "BepInEx");
    var core = Path.Combine(bepin, "core");
    Directory.CreateDirectory(core);
    var context = new BootstrapContext(game, core, bepin, Path.Combine(game, "GameAssembly.dll"),
        Path.Combine(game, "UnityPlayer.dll"), Path.Combine(game, "original-metadata.dat"),
        Path.Combine(game, "doorstop_api.ini"),
        Path.Combine(core, "bootstrap.dll"),
        Path.Combine(bepin, "cache", "metadata", "global-metadata.dat"), Path.Combine(bepin, "config", "BepInEx.cfg"));
    File.WriteAllText(context.GameAssemblyPath, "inert game fingerprint fixture");
    File.WriteAllText(context.UnityPlayerPath, "inert Unity fingerprint fixture");
    File.WriteAllText(context.OriginalMetadataPath, "inert metadata fixture");
    File.WriteAllText(context.ApiMapPath, "[Exports]\ninert=fixture\n");
    File.WriteAllText(context.DecoderPath, "inert decoder fingerprint fixture");
    File.WriteAllText(Path.Combine(core, "Iced.dll"), "inert Iced fingerprint fixture");
    return context;
}
try
{
    Test("config preserves other settings and is idempotent", () =>
    {
        var input = "# comment\r\n[Logging]\r\nEnabled = true\r\n[IL2CPP]\r\nOther = retain\r\nGlobalMetadataPath = old\r\n[Graphics]\r\nQuality = 3\r\n";
        var output = Bootstrap.UpdateMetadataConfig(input, "{BepInEx}/cache/metadata/global-metadata.dat");
        Check(output.Contains("Other = retain\r\n") && output.Contains("[Graphics]\r\nQuality = 3\r\n"), "Other settings changed");
        Check(output.StartsWith("# comment\r\n[Logging]\r\nEnabled = true\r\n"), "Other sections changed");
        Check(Bootstrap.UpdateMetadataConfig(output, "{BepInEx}/cache/metadata/global-metadata.dat") == output, "Config update is not idempotent");
        Check(Bootstrap.UpdateMetadataConfig("[IL2CPP]\nOther=1\n[Other]\nX=2", "new").Contains("GlobalMetadataPath = new\n[Other]"), "New key inserted outside IL2CPP");
    });
    Test("cache reuse requires input and output identities", () =>
    {
        var context = Context("cache identity");
        var log = Path.Combine(context.BepInExRoot, "metadata-bootstrap.log");
        var calls = 0;
        void Decode(BootstrapContext _, string output, string __) { calls++; File.WriteAllBytes(output, ValidMetadata()); }
        Bootstrap.Prepare(context, log, Decode);
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 1, "Valid cache was not reused");
        File.AppendAllText(context.GameAssemblyPath, " changed");
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 2, "Changed game was not detected");
        File.AppendAllText(context.OutputPath, "corruption");
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 3, "Corrupted output was not detected");
        File.AppendAllText(context.DecoderPath, " changed");
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 4, "Changed decoder was not detected");
        File.AppendAllText(context.ApiMapPath, " changed");
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 5, "Changed API map was not detected");
        File.AppendAllText(Path.Combine(context.CoreDirectory, "Iced.dll"), " changed");
        Bootstrap.Prepare(context, log, Decode);
        Check(calls == 6, "Changed disassembler was not detected");
    });
    Test("bad decoder output cannot publish config or cache", () =>
    {
        var context = Context("invalid output");
        var log = Path.Combine(context.BepInExRoot, "metadata-bootstrap.log");
        try
        {
            Bootstrap.Prepare(context, log, (_, output, _) => File.WriteAllText(output, "invalid"));
            throw new Exception("Expected invalid output rejection");
        }
        catch (InvalidDataException) { }
        Check(!File.Exists(context.ConfigPath) && !File.Exists(context.OutputPath), "Invalid output was published");
        Check(!Directory.GetFiles(Path.GetDirectoryName(context.OutputPath)!).Any(), "Temporary output was not cleaned up");
    });
    Test("inputs changing during decode cannot publish cache", () =>
    {
        var context = Context("input race");
        var log = Path.Combine(context.BepInExRoot, "metadata-bootstrap.log");
        try
        {
            Bootstrap.Prepare(context, log, (_, output, _) => { File.WriteAllBytes(output, ValidMetadata()); File.AppendAllText(context.OriginalMetadataPath, " update"); });
            throw new Exception("Expected changed input rejection");
        }
        catch (IOException) { }
        Check(!File.Exists(context.ConfigPath) && !File.Exists(context.OutputPath), "Racing input output was published");
    });

    foreach (var version in new[] { 38, 39 })
        Test($"standard schema {version} bootstrap with no generated API map", () =>
        {
            var context = Context($"managed decoder schema {version} with spaces");
            File.Delete(context.ApiMapPath);
            File.Copy(Path.Combine(AppContext.BaseDirectory, "Iced.dll"), Path.Combine(context.CoreDirectory, "Iced.dll"), true);
            File.WriteAllText(context.UnityPlayerPath, version == 38 ? "6000.3.0a5" : "6000.3.0b1", System.Text.Encoding.Unicode);
            var original = StandardMetadata(version);
            File.WriteAllBytes(context.OriginalMetadataPath, original);
            var log = Path.Combine(context.BepInExRoot, "metadata-bootstrap.log");
            Bootstrap.Prepare(context, log);
            Check(File.ReadAllBytes(context.OutputPath).AsSpan().SequenceEqual(original), "Standard metadata changed");
            Check(File.Exists(context.OutputPath + ".evidence.json"), "Decoder evidence was not published");
            Check(!Directory.GetFiles(Path.GetDirectoryName(context.OutputPath)!).Any(path => path.Contains(".partial")), "Temporary evidence was not cleaned up");
            Bootstrap.Prepare(context, log);
            Check(File.ReadAllText(log).Contains("Validated the metadata cache"), "Managed cache was not reused");
            File.WriteAllText(context.UnityPlayerPath, "6000.5.0a3", System.Text.Encoding.Unicode);
            try
            {
                Bootstrap.Prepare(context, log);
                throw new Exception("Expected unsupported Unity schema rejection");
            }
            catch (InvalidDataException error) when (error.Message.Contains("newer metadata schema")) { }
            Check(File.ReadAllBytes(context.OutputPath).AsSpan().SequenceEqual(original), "Failed refresh replaced the prior valid output");
            Check(!Bootstrap.CacheIsValid(context.OutputPath, context.OutputPath + ".fingerprint.json",
                Bootstrap.Fingerprint(context)), "Prior cache accepted changed input after failed refresh");
        });


    foreach (var version in new[] { 38, 39 })
        Test($"obfuscated schema {version} reconstruction with independent native ranges", () =>
        {
            var standard = StandardMetadata(version);
            var (encoded, native) = Obfuscate(standard);
            var (normalized, _) = MetadataNormalizer.Normalize(encoded, version, native);
            Check(normalized.AsSpan().SequenceEqual(standard), "Obfuscated fixture did not reconstruct byte for byte");
            var sections = (NativeSection[])native.Sections.Clone();
            sections[0] = sections[0] with { Constant = sections[0].Constant + 1 };
            try
            {
                MetadataNormalizer.Normalize(encoded, version, native with { Sections = sections });
                throw new Exception("Expected native XOR disagreement to be rejected");
            }
            catch (InvalidDataException error) when (error.Message.Contains("disagree with native decoder semantics")) { }
        });

    if (args.Length != 0)
    {
        if (args.Length != 7 || args[0] != "--cold-fixture")
            throw new ArgumentException("Usage: MetadataBootstrap.Tests [--cold-fixture <GameAssembly> <UnityPlayer> <metadata> <API map> <expected SHA-256> <new output directory>]");
        Test("cold obfuscated fixture matches the legacy decoder SHA-256", () =>
        {
            var outputRoot = Path.GetFullPath(args[6]);
            if (Directory.Exists(outputRoot) || File.Exists(outputRoot))
                throw new IOException("The cold fixture output directory must be new.");
            var bepin = Path.Combine(outputRoot, "BepInEx");
            var context = Context("cold fixture") with
            {
                GameAssemblyPath = Path.GetFullPath(args[1]), UnityPlayerPath = Path.GetFullPath(args[2]),
                OriginalMetadataPath = Path.GetFullPath(args[3]), ApiMapPath = Path.GetFullPath(args[4]),
                BepInExRoot = bepin, OutputPath = Path.Combine(bepin, "cache", "metadata", "global-metadata.dat"),
                ConfigPath = Path.Combine(bepin, "config", "BepInEx.cfg"),
                DecoderPath = typeof(Bootstrap).Assembly.Location,
            };
            var originalIced = Path.Combine(AppContext.BaseDirectory, "Iced.dll");
            File.Copy(originalIced, Path.Combine(context.CoreDirectory, "Iced.dll"), true);
            var inputs = Bootstrap.Fingerprint(context);
            var log = Path.Combine(bepin, "metadata-bootstrap.log");
            var testMap = Path.Combine(temporary, "invalid-map.ini");
            var map = File.ReadAllText(context.ApiMapPath);
            void RejectMap(string invalidMap, string message)
            {
                Check(invalidMap != map, "The fixture API map did not contain the expected test entry");
                File.WriteAllText(testMap, invalidMap);
                try
                {
                    Bootstrap.Prepare(context with { ApiMapPath = testMap }, log);
                    throw new Exception("Expected the modified API map to be rejected");
                }
                catch (InvalidDataException error) when (error.Message.Contains(message)) { }
                Check(!File.Exists(context.OutputPath) && !File.Exists(context.ConfigPath), "Invalid map published a cache or config");
            }
            RejectMap(System.Text.RegularExpressions.Regex.Replace(map, "(?m)^TimeDateStamp=[0-9a-fA-F]+", "TimeDateStamp=0"), "identity does not match");
            RejectMap(System.Text.RegularExpressions.Regex.Replace(map, "(?m)^il2cpp_init=[^,]+,", "il2cpp_init=NoMatchingExport,"), "alias and RVA do not match");
            Bootstrap.Prepare(context, log);
            var actual = Bootstrap.HashFile(context.OutputPath);
            Check(actual.Equals(args[5], StringComparison.OrdinalIgnoreCase), $"Unexpected normalized hash {actual}");
            Check(inputs == Bootstrap.Fingerprint(context), "Cold decode changed its inputs");
            Check(File.ReadAllText(context.ConfigPath).Contains("{BepInEx}/cache/metadata/global-metadata.dat"), "BepInEx metadata path was not configured");
            Bootstrap.Prepare(context, log);
            Check(File.ReadAllText(log).Contains("Validated the metadata cache"), "Cold fixture cache was not reused");
            Console.WriteLine($"Normalized SHA-256 {actual}");
        });
    }

    Console.WriteLine($"{passed} tests passed.");
    return 0;
}
finally
{
    var resolved = Path.GetFullPath(temporary);
    var tempRoot = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
    if (!resolved.StartsWith(tempRoot, StringComparison.OrdinalIgnoreCase)
        || !Path.GetFileName(resolved).StartsWith("Metadata bootstrap tests ", StringComparison.Ordinal))
        throw new InvalidOperationException("Refusing cleanup outside the test's temporary directory.");
    Directory.Delete(resolved, recursive: true);
}
