using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using AssetRipper.Primitives;
using LibCpp2IL.Metadata;

try
{
    var options = new Dictionary<string, string>(StringComparer.Ordinal);
    for (var index = 0; index < args.Length; index += 2)
    {
        if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
            throw new ArgumentException("Usage: MetadataProbe --metadata <file> --unity <UnityPlayer.dll> [--output <json>]");
        options.Add(args[index], args[index + 1]);
    }
    var metadataPath = Path.GetFullPath(options["--metadata"]);
    var unityPath = Path.GetFullPath(options["--unity"]);
    var fileVersion = FileVersionInfo.GetVersionInfo(unityPath);
    var version = UnityVersion.Parse((fileVersion.ProductVersion ?? throw new InvalidDataException("UnityPlayer has no product version.")).Split(' ', 2)[0]);
    var bytes = File.ReadAllBytes(metadataPath);
    var parsed = Il2CppMetadata.ReadFrom(bytes, version);
    var fieldDefinitions = (Array)(typeof(Il2CppMetadata).GetField("fieldDefs", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)?.GetValue(parsed)
                                  ?? throw new InvalidDataException("The BepInEx metadata parser does not expose its field definition table."));
    var counts = new Dictionary<string, int>
    {
        ["type_definitions"] = parsed.typeDefs.Length,
        ["methods"] = parsed.methodDefs.Length,
        ["fields"] = fieldDefinitions.Length,
        ["images"] = parsed.imageDefinitions.Length,
        ["assemblies"] = parsed.AssemblyDefinitions.Length
    };
    if (counts.Values.Any(count => count <= 0))
        throw new InvalidDataException("The parser returned an empty essential metadata table.");
    if (counts["images"] != counts["assemblies"])
        throw new InvalidDataException("Image and assembly counts disagree.");

    var namesChecked = 0;
    var examples = new Dictionary<string, string[]>();
    void ValidateNames(Array records, string label)
    {
        var elementType = records.GetType().GetElementType()!;
        var field = elementType.GetField("nameIndex", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.IgnoreCase)
                    ?? throw new InvalidDataException($"{elementType.FullName} has no nameIndex field. Fields: {string.Join(",", elementType.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic).Select(f => f.Name))}. Properties: {string.Join(",",elementType.GetProperties().Select(p => p.Name))}");
        var examplesForTable = new List<string>();
        foreach (var record in records)
        {
            var value = field.GetValue(record)!;
            int nameIndex;
            if (value is IConvertible) nameIndex = Convert.ToInt32(value);
            else
            {
                var type = value.GetType();
                var boxedIndex = type.GetField("Value", BindingFlags.Public | BindingFlags.Instance)?.GetValue(value)
                                 ?? type.GetProperty("Value", BindingFlags.Public | BindingFlags.Instance)?.GetValue(value)
                                 ?? throw new InvalidDataException($"Unsupported name index wrapper {type.FullName}.");
                nameIndex = Convert.ToInt32(boxedIndex);
            }
            if (nameIndex < 0) throw new InvalidDataException($"Negative {label} name index.");
            var name = parsed.GetStringFromIndex(nameIndex);
            if (string.IsNullOrEmpty(name) || name.Contains('\uFFFD'))
                throw new InvalidDataException($"Invalid {label} name at string index {nameIndex}.");
            namesChecked++;
            if (examplesForTable.Count < 3) examplesForTable.Add(name);
        }
        examples[label] = examplesForTable.ToArray();
    }
    ValidateNames(parsed.typeDefs, "types");
    ValidateNames(parsed.methodDefs, "methods");
    ValidateNames(fieldDefinitions, "fields");
    ValidateNames(parsed.imageDefinitions, "images");

    var evidencePath = metadataPath + ".evidence.json";
    var evidenceCountsAgree = false;
    if (File.Exists(evidencePath))
    {
        using var evidence = JsonDocument.Parse(File.ReadAllText(evidencePath));
        var validation = evidence.RootElement.GetProperty("validation");
        foreach (var (key, value) in counts)
            if (validation.GetProperty(key).GetInt32() != value)
                throw new InvalidDataException($"The exact BepInEx parser count for {key} disagrees with the normalizer's independent validation.");
        evidenceCountsAgree = true;
    }
    var result = new
    {
        success = true,
        metadata = metadataPath,
        unity = unityPath,
        unityVersion = version.ToString(),
        metadataVersion = BitConverter.ToInt32(bytes, 4),
        parserAssembly = typeof(Il2CppMetadata).Assembly.FullName,
        counts,
        namesChecked,
        examples,
        evidenceCountsAgree
    };
    var json = JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true });
    if (options.TryGetValue("--output", out var output))
    {
        var outputPath = Path.GetFullPath(output);
        Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
        File.WriteAllText(outputPath, json);
    }
    Console.WriteLine(json);
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error);
    return 1;
}
