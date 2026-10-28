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
var temporary = Path.Combine(Path.GetTempPath(), "Metadata bootstrap tests " + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(temporary);
BootstrapContext Context(string name)
{
    var game = Path.Combine(temporary, name);
    var bepin = Path.Combine(game, "BepInEx");
    var core = Path.Combine(bepin, "core");
    Directory.CreateDirectory(Path.Combine(core, "scripts"));
    var context = new BootstrapContext(game, core, bepin, Path.Combine(game, "GameAssembly.dll"),
        Path.Combine(game, "UnityPlayer.dll"), Path.Combine(game, "original-metadata.dat"),
        Path.Combine(game, "doorstop_api.ini"),
        Path.Combine(core, "scripts", "normalize_metadata.py"),
        Path.Combine(bepin, "cache", "metadata", "global-metadata.dat"), Path.Combine(bepin, "config", "BepInEx.cfg"));
    File.WriteAllText(context.GameAssemblyPath, "inert game fingerprint fixture");
    File.WriteAllText(context.UnityPlayerPath, "inert Unity fingerprint fixture");
    File.WriteAllText(context.OriginalMetadataPath, "inert metadata fixture");
    File.WriteAllText(context.ApiMapPath, "[Exports]\ninert=fixture\n");
    File.WriteAllText(context.DecoderPath, "# inert decoder fingerprint fixture");
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
    Test("Python arguments round-trip with spaces and evidence is published", () =>
    {
        var context = Context("python path with spaces");
        File.WriteAllText(context.DecoderPath, "import argparse,struct,json,pathlib\np=argparse.ArgumentParser()\np.add_argument('--game',required=True)\np.add_argument('--metadata',required=True)\np.add_argument('--api-map',required=True)\np.add_argument('--output',required=True)\na=p.parse_args()\nassert pathlib.Path(a.game).is_file() and pathlib.Path(a.metadata).is_file() and pathlib.Path(a.api_map).is_file()\npathlib.Path(a.output).write_bytes(struct.pack('<IIIII',0xFAB11BAF,39,20,12,3)+bytes(12))\npathlib.Path(a.output+'.evidence.json').write_text(json.dumps(vars(a)))\nprint('decoder fixture completed')\n");
        Bootstrap.Prepare(context, Path.Combine(context.BepInExRoot, "metadata-bootstrap.log"));
        Check(File.Exists(context.OutputPath + ".evidence.json"), "Decoder evidence was not published");
        Check(!Directory.GetFiles(Path.GetDirectoryName(context.OutputPath)!).Any(path => path.Contains(".partial")), "Temporary evidence was not cleaned up");
    });
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
