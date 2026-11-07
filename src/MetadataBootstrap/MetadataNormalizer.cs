using System.Buffers.Binary;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace BepInEx.MetadataBootstrap;

internal static class MetadataNormalizer
{
    internal const uint Magic = 0xFAB11BAF;
    internal const int HeaderSize = 8 + 12 * 31;

    private static readonly string[] Names =
    {
        "StringLiterals", "StringLiteralData", "Strings", "Events", "Properties", "Methods",
        "ParameterDefaultValues", "FieldDefaultValues", "FieldAndParameterDefaultValueData",
        "FieldMarshaledSizes", "Parameters", "Fields", "GenericParameters", "GenericParameterConstraints",
        "GenericContainers", "NestedTypes", "Interfaces", "VtableMethods", "InterfaceOffsets",
        "TypeDefinitions", "Images", "Assemblies", "FieldRefs", "ReferencedAssemblies", "AttributeData",
        "AttributeDataRange", "UnresolvedVirtualCallParameterTypes", "UnresolvedVirtualCallParameterRanges",
        "WindowsRuntimeTypeNames", "WindowsRuntimeStrings", "ExportedTypeDefinitions",
    };

    private static readonly int[] Encrypted = { 0, 1, 2, 4, 5, 11, 21 };
    private static readonly int[] FixedStrides =
    {
        4, 0, 0, 0, 20, 0, 0, 0, 1, 0, 0, 0, 0, 0, 16, 4, 0, 4, 0, 0, 0, 68, 0, 4, 0, 8, 0, 8, 0, 0, 4,
    };
    private static readonly (int Offset, int Size, int Count)[] Orders =
    {
        (0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0),
    };
    private static readonly Regex UnityVersion = new(@"(?<![0-9])([0-9]{4}|[0-9]{1,2})\.([0-9]+)\.([0-9]+)([abfp])([0-9]+)",
        RegexOptions.CultureInvariant);
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    private readonly record struct Section(int Claimed, int Size, int Count, int Slot, int Start = 0);
    private sealed record Widths(int Type, int TypeDefinition, int GenericContainer, int Parameter, int[] Strides);
    private sealed record KeyFamily(bool UseSize, int Addend, int[] Keys);

    internal static void Decode(BootstrapContext context, string output, string log)
    {
        var (unity, version) = GetSchema(context.UnityPlayerPath);
        var raw = File.ReadAllBytes(context.OriginalMetadataPath);
        byte[] normalized;
        Dictionary<string, object> evidence;
        if (raw.Length >= 8 && U32(raw, 0) == Magic)
        {
            normalized = raw;
            evidence = new Dictionary<string, object>
            {
                ["method"] = "already-standard-validated",
                ["validation"] = ValidateStandard(raw, version),
            };
        }
        else
        {
            var native = NativeMetadataDecoder.Infer(context.GameAssemblyPath, context.ApiMapPath);
            (normalized, evidence) = Normalize(raw, version, native);
        }
        evidence["schema_version"] = 1;
        evidence["metadata_version"] = version;
        evidence["unity_version"] = unity;
        evidence["input_size"] = raw.Length;
        evidence["output_size"] = normalized.Length;
        evidence["input_sha256"] = Hash(raw);
        evidence["output_sha256"] = Hash(normalized);
        evidence["game_sha256"] = Bootstrap.HashFile(context.GameAssemblyPath).ToLowerInvariant();

        File.WriteAllBytes(output, normalized);
        File.WriteAllText(output + ".evidence.json", JsonSerializer.Serialize(evidence, JsonOptions) + "\n");
        Bootstrap.Log(log, $"Validated metadata schema {version} for Unity {unity} in process.");
    }

    private static (string Version, int Schema) GetSchema(string playerPath)
    {
        var match = UnityVersion.Match(Encoding.Unicode.GetString(File.ReadAllBytes(playerPath)));
        if (!match.Success)
            throw new InvalidDataException("Cannot read a Unity product version from UnityPlayer.dll.");
        int Number(int group) => int.Parse(match.Groups[group].Value, CultureInfo.InvariantCulture);
        var version = (Number(1), Number(2), Number(3), "abfp".IndexOf(match.Groups[4].Value[0]), Number(5));
        if (version.CompareTo((6000, 3, 0, 0, 5)) < 0)
            throw new InvalidDataException("This normalizer requires metadata schema 38 or 39.");
        if (version.CompareTo((6000, 5, 0, 0, 3)) >= 0)
            throw new InvalidDataException("This Unity release uses a newer metadata schema.");
        return (match.Value, version.CompareTo((6000, 3, 0, 1, 1)) < 0 ? 38 : 39);
    }

    private static object ValidateStandard(byte[] raw, int version)
    {
        if (raw.Length < HeaderSize || U32(raw, 4) != version)
            throw new InvalidDataException("Standard metadata header does not match the engine's schema.");
        var sections = new Section[Names.Length];
        for (var i = 0; i < sections.Length; i++)
        {
            var at = 8 + i * 12;
            var start = U32(raw, at);
            var size = U32(raw, at + 4);
            var count = U32(raw, at + 8);
            if ((size != 0 && (start < HeaderSize || (long)start + size > raw.Length || count > size))
                || (size == 0 && count != 0))
                throw new InvalidDataException($"Standard metadata section {Names[i]} has an invalid range or count.");
            sections[i] = new Section(size == 0 ? 0 : (int)start, (int)size, (int)count, i * 12, size == 0 ? 0 : (int)start);
        }
        return ValidateTables(raw, sections, new byte[Names.Length][], CheckStrides(sections, version));
    }

    internal static (byte[] Output, Dictionary<string, object> Evidence) Normalize(byte[] raw, int version, NativeDecoder native)
    {
        var length = native.Header.Length;
        if (length < 12 * Names.Length || length % 12 != 0 || length > raw.Length - 4)
            throw new InvalidDataException("Native metadata header length is outside the expected triple table bounds.");
        for (var i = 0; i < 4; i++)
            if (raw[length + i] != (byte)(raw[length] + i))
                throw new InvalidDataException("The native header length does not lead to a rotating string literal offset.");

        var header = new byte[length];
        Xor(raw.AsSpan(0, length), header, native.Header.Key);
        var nativeRanges = ResolveNativeRanges(raw.Length, header, native);
        byte[]? output = null;
        Dictionary<string, object>? evidence = null;
        string? lastError = null;
        foreach (var order in Orders)
        {
            var candidates = new List<Section>();
            for (var at = 0; at < length; at += 12)
            {
                var claimed = U32(header, at + order.Offset * 4);
                var size = U32(header, at + order.Size * 4);
                var count = U32(header, at + order.Count * 4);
                if (claimed < length - 128 || claimed >= raw.Length || count > size || size > raw.Length
                    || (long)claimed + size > (long)raw.Length + 128
                    || (size != 0 && (count == 0 || (long)count * 256 < size))) continue;
                candidates.Add(new Section((int)claimed, (int)size, (int)count, at));
            }
            if (candidates.Count < Names.Length) continue;
            var ordered = candidates.OrderBy(section => section.Claimed).ThenBy(section => section.Slot).ToArray();
            foreach (var sections in FindLayouts(raw.Length, length, ordered))
            {
                byte[] reconstructed;
                Dictionary<string, object> trace;
                try
                {
                    var widths = CheckStrides(sections, version);
                    var family = FindKeyFamily(raw, sections, widths);
                    var clear = new byte[Names.Length][];
                    foreach (var index in Encrypted)
                    {
                        var section = sections[index];
                        clear[index] = new byte[section.Size];
                        Xor(raw.AsSpan(section.Start, section.Size), clear[index], family.Keys[index]);
                    }

                    var nativeEvidence = ValidateNative(raw, sections, clear, nativeRanges, order.Offset, order.Size);
                    var validation = ValidateTables(raw, sections, clear, widths);
                    reconstructed = Reconstruct(raw, sections, clear, length, version);
                    trace = new Dictionary<string, object>
                    {
                        ["method"] = "structural-and-native-validated",
                        ["header_length"] = length,
                        ["header_xor_key"] = native.Header.Key,
                        ["header_xor_direction"] = 1,
                        ["triple_order"] = new { offset = order.Offset, size = order.Size, count = order.Count },
                        ["index_widths"] = new
                        {
                            type = widths.Type, type_definition = widths.TypeDefinition,
                            generic_container = widths.GenericContainer, parameter = widths.Parameter,
                        },
                        ["section_xor"] = new
                        {
                            component = family.UseSize ? "size" : "start",
                            addend = family.Addend,
                            keys = Encrypted.ToDictionary(index => Names[index], index => family.Keys[index]),
                        },
                        ["validation"] = validation,
                        ["sections"] = sections.Select((section, index) => new
                        {
                            name = Names[index], source_start = section.Start, source_claimed_offset = section.Claimed,
                            source_offset_delta = section.Start - section.Claimed, source_header_slot = section.Slot,
                            size = section.Size, count = section.Count,
                        }).ToArray(),
                        ["native_validation"] = new
                        {
                            format = 1, method = "verified-init-callgraph-and-native-decoder-dataflow",
                            init_rva = Hex(native.InitRva), function_rva = Hex(native.FunctionRva),
                            native_functions_examined = native.FunctionsExamined,
                            header = new { length, key = native.Header.Key, loop_rva = Hex(native.Header.LoopRva) },
                            sections = nativeEvidence,
                        },
                    };
                }
                catch (InvalidDataException error)
                {
                    lastError = error.Message;
                    continue;
                }

                if (output is not null && !output.AsSpan().SequenceEqual(reconstructed))
                    throw new InvalidDataException("Multiple distinct metadata reconstructions passed validation.");
                output = reconstructed;
                evidence = trace;
            }
        }
        if (output is null)
            throw new InvalidDataException("No metadata reconstruction passed validation."
                + (lastError is null ? "" : " Last rejection was " + lastError));
        return (output, evidence!);
    }

    private static List<Section[]> FindLayouts(int fileSize, int headerLength, Section[] candidates)
    {
        var layouts = new List<Section[]>();
        var sections = new Section[Names.Length];
        var used = new bool[headerLength / 12];
        var visited = 0;

        void Walk(int index, int position)
        {
            if (++visited > 100000 || layouts.Count >= 256)
                throw new InvalidDataException("Metadata layout exceeds its ambiguity bound.");
            if (index == Names.Length)
            {
                layouts.Add((Section[])sections.Clone());
                return;
            }
            var alignment = index == 8 ? 8 : 4;
            var canonical = (long)position + HeaderSize - headerLength;
            var aligned = position + ((-canonical) & (alignment - 1));
            if (aligned > fileSize) return;
            position = (int)aligned;
            foreach (var section in candidates)
            {
                var delta = Math.Abs((long)position - section.Claimed);
                if (delta is < 16 or > 64 || used[section.Slot / 12] || (long)position + section.Size > fileSize)
                    continue;
                if (index < 26 && section.Count == 0) continue;
                var fixedStride = FixedStrides[index];
                if (fixedStride != 0 && section.Size != (long)section.Count * fixedStride) continue;
                sections[index] = section with { Start = position };
                used[section.Slot / 12] = true;
                Walk(index + 1, position + section.Size);
                used[section.Slot / 12] = false;
            }
        }

        Walk(0, headerLength);
        return layouts;
    }

    private static Widths CheckStrides(Section[] sections, int version)
    {
        static int IndexWidth(int count) => count <= byte.MaxValue ? 1 : count <= ushort.MaxValue ? 2 : 4;
        var td = IndexWidth(sections[19].Count);
        var gc = IndexWidth(sections[14].Count);
        var parameter = version >= 39 ? IndexWidth(sections[10].Count) : 4;
        Widths? result = null;
        foreach (var type in new[] { 1, 2, 4 })
        {
            int[] strides =
            {
                4, 0, 0, 20 + type, 20, 20 + td + type + parameter + gc, parameter + type + 4,
                8 + type, 1, 8 + type, 8 + type, 8 + type, 12 + gc, type, 16, 4, type, 4, 4 + type,
                68 + 3 * type + gc, 32 + 2 * td, 68, type + 4, 4, 0, 8, type, 8, 4 + type, 0, 4,
            };
            if (strides.Where((stride, index) => stride != 0
                && sections[index].Size != (long)sections[index].Count * stride).Any())
                continue;
            if (result is not null) throw new InvalidDataException("Variable-width metadata schema is ambiguous.");
            result = new Widths(type, td, gc, parameter, strides);
        }
        return result ?? throw new InvalidDataException("No variable-width metadata schema matches all table strides.");
    }

    private static KeyFamily FindKeyFamily(byte[] raw, Section[] sections, Widths widths)
    {
        var literalKey = raw[sections[0].Start];
        KeyFamily? result = null;
        Span<byte> probe = stackalloc byte[64];
        foreach (var useSize in new[] { true, false })
        foreach (var literalSign in new[] { 1, -1 })
        {
            int Component(Section section) => useSize ? section.Size : section.Start;
            var addend = (literalSign * literalKey - Component(sections[0])) & 255;
            var keys = new int[Names.Length];
            var matches = true;
            foreach (var index in Encrypted)
            {
                var section = sections[index];
                var encryptedProbe = raw.AsSpan(section.Start, Math.Min(section.Size, probe.Length));
                var key = (Component(section) + addend) & 255;
                Xor(encryptedProbe, probe, key);
                var positive = ValidProbe(index, probe[..encryptedProbe.Length], widths);
                var negativeKey = (-key) & 255;
                Xor(encryptedProbe, probe, negativeKey);
                var negative = ValidProbe(index, probe[..encryptedProbe.Length], widths);
                if ((!positive && !negative) || (positive && negative && key != negativeKey))
                {
                    matches = false;
                    break;
                }
                keys[index] = positive ? key : negativeKey;
            }
            if (!matches) continue;
            if (result is not null && !result.Keys.AsSpan().SequenceEqual(keys))
                throw new InvalidDataException("Section-key family remains ambiguous.");
            result = new KeyFamily(useSize, addend, keys);
        }
        return result ?? throw new InvalidDataException("No common rotating section-key family passed all seven probes.");
    }

    private static bool ValidProbe(int index, ReadOnlySpan<byte> probe, Widths widths)
    {
        switch (index)
        {
            case 0: return MatchesWord(probe, 0, 0);
            case 1: return probe.Length >= 2 && probe[0] == 0 && probe[1] == 0;
            case 2:
                foreach (var value in probe)
                    if (value != 0 && (value < 32 || value == 127)) return false;
                return probe.Contains((byte)0);
            case 4: return MatchesWord(probe, 16, 0x17000001);
            case 5: return MatchesWord(probe,
                8 + widths.TypeDefinition + widths.Type + widths.Parameter + widths.GenericContainer, 0x06000001);
            case 11: return MatchesWord(probe, 4 + widths.Type, 0x04000001);
            case 21: return MatchesWord(probe, 0, 0) && MatchesWord(probe, 4, 0x20000001);
            default: throw new InvalidOperationException("Unknown metadata probe.");
        }
    }

    private static bool MatchesWord(ReadOnlySpan<byte> data, int at, uint expected) =>
        at <= data.Length - 4 && U32(data, at) == expected;

    private static object ValidateTables(byte[] raw, Section[] sections, byte[][] clear, Widths widths)
    {
        ReadOnlySpan<byte> Table(int index) => clear[index] is { } decoded
            ? decoded : raw.AsSpan(sections[index].Start, sections[index].Size);

        var literals = Table(0);
        if ((long)sections[0].Count != (long)sections[1].Count + 1 || !MatchesWord(literals, 0, 0))
            throw new InvalidDataException("String literal offsets and counts do not agree with literal data.");
        uint last = 0;
        for (var at = 4; at < literals.Length; at += 4)
        {
            var offset = U32(literals, at);
            if (offset < last || offset > sections[1].Size)
                throw new InvalidDataException("String literal offsets are outside literal data or out of order.");
            last = offset;
        }

        var types = Table(19);
        var stride = widths.Strides[19];
        var sums = new long[8];
        for (var at = 0; at < types.Length; at += stride)
            for (var field = 0; field < sums.Length; field++)
                sums[field] += BinaryPrimitives.ReadUInt16LittleEndian(types[(at + stride - 24 + field * 2)..]);
        int[] members = { 5, 4, 11, 3, 15, 17, 16, 18 };
        for (var i = 0; i < members.Length; i++)
            if (sums[i] != sections[members[i]].Count)
                throw new InvalidDataException($"Type member counts disagree with {Names[members[i]]}.");

        var images = Table(20);
        var td = widths.TypeDefinition;
        long typeSum = 0, exportSum = 0, attributeSum = 0;
        for (var at = 0; at < images.Length; at += widths.Strides[20])
        {
            typeSum += U32(images, at + 8 + td);
            exportSum += U32(images, at + 12 + 2 * td);
            attributeSum += U32(images, at + 28 + 2 * td);
        }
        if (typeSum != sections[19].Count || sections[20].Count != sections[21].Count
            || exportSum != sections[30].Count || attributeSum + 1 != sections[25].Count)
            throw new InvalidDataException("Image type, export, assembly, or attribute totals do not match their tables.");

        var ranges = Table(25);
        if (!MatchesWord(ranges, 4, 0))
            throw new InvalidDataException("Custom attribute ranges must begin at zero.");
        last = 0;
        for (var at = 4; at < ranges.Length; at += 8)
        {
            var start = U32(ranges, at);
            if (start < last) throw new InvalidDataException("Custom attribute ranges are out of order.");
            last = start;
        }
        if (last > sections[24].Size || sections[24].Size > (long)last + 3)
            throw new InvalidDataException("Custom attribute ranges do not tile attribute data.");

        long next = 0;
        var calls = Table(27);
        for (var at = 0; at < calls.Length; at += 8)
        {
            if (U32(calls, at) != next || U32(calls, at + 4) > int.MaxValue)
                throw new InvalidDataException("Unresolved virtual call ranges are discontinuous.");
            next += U32(calls, at + 4);
        }
        if (next != sections[26].Count)
            throw new InvalidDataException("Unresolved virtual call ranges do not cover parameter types.");

        var strings = Table(2);
        foreach (var index in new[] { 19, 20, 5, 11 })
        {
            var table = Table(index);
            for (var at = 0; at < table.Length; at += widths.Strides[index])
            {
                var offset = U32(table, at);
                if (offset >= strings.Length || !strings[(int)offset..].Contains((byte)0))
                    throw new InvalidDataException($"{Names[index]} contains an invalid string index.");
            }
        }

        return new
        {
            type_definitions = sections[19].Count, methods = sections[5].Count, fields = sections[11].Count,
            images = sections[20].Count, assemblies = sections[21].Count, string_literals = sections[1].Count,
            checks = new[]
            {
                "all schema strides", "all literal offsets", "all type member totals", "image table totals",
                "attribute range coverage", "virtual-call range coverage", "all type/image/method/field name indices",
            },
        };
    }

    private sealed record NativeRange(NativeSection Section, int Start, int Size);

    private static NativeRange[] ResolveNativeRanges(int rawLength, byte[] header, NativeDecoder native)
    {
        var ranges = new List<NativeRange>();
        foreach (var section in native.Sections)
        {
            if (section.SizeField < 0 || section.SizeField > header.Length - 4
                || section.OffsetField < 0 || section.OffsetField > header.Length - 4)
                throw new InvalidDataException("Native metadata field lies outside the inferred header.");
            var size = U32(header, (int)section.SizeField);
            var start = U32(header, (int)section.OffsetField) + section.Adjustment;
            if (start < header.Length || start + size > rawLength)
                throw new InvalidDataException("An inferred native section lies outside metadata.");
            ranges.Add(new NativeRange(section, (int)start, (int)size));
        }
        var end = header.Length;
        foreach (var range in ranges.Where(range => range.Size != 0).OrderBy(range => range.Start))
        {
            if (range.Start < end) throw new InvalidDataException("Inferred native metadata sections overlap.");
            end = range.Start + range.Size;
        }
        return ranges.ToArray();
    }

    private static object[] ValidateNative(byte[] raw, Section[] sections, byte[][] clear, NativeRange[] ranges,
        int offsetWord, int sizeWord)
    {
        var matched = new HashSet<int>();
        var evidence = new List<object>();
        foreach (var range in ranges)
        {
            var index = -1;
            for (var i = 0; i < sections.Length; i++)
            {
                if (sections[i].Start != range.Start || sections[i].Size != range.Size) continue;
                if (index != -1) throw new InvalidDataException("An inferred native range matches multiple metadata tables.");
                index = i;
            }
            if (index == -1 || clear[index] is not { } decoded || !matched.Add(index))
                throw new InvalidDataException("Native and structural decoders disagree on encrypted table ranges.");

            var native = range.Section;
            var section = sections[index];
            if (section.Slot + offsetWord * 4 != native.OffsetField || section.Slot + sizeWord * 4 != native.SizeField)
                throw new InvalidDataException("Native and structural decoders disagree on header field placement.");

            var key = native.SizeCoefficient * range.Size + native.Constant;
            var encrypted = raw.AsSpan(range.Start, range.Size);
            for (var at = 0; at < encrypted.Length; at++)
                if (decoded[at] != (byte)(encrypted[at] ^ (byte)(key + at)))
                    throw new InvalidDataException($"{Names[index]} bytes disagree with native decoder semantics.");
            evidence.Add(new
            {
                name = Names[index], file_offset = range.Start, byte_size = range.Size,
                size_field = native.SizeField, offset_field = native.OffsetField, offset_adjustment = native.Adjustment,
                xor_index_coefficient = 1, xor_size_coefficient = native.SizeCoefficient, xor_constant = native.Constant,
                allocation_rva = Hex(native.AllocationRva), copy_rva = Hex(native.CopyRva), xor_rva = Hex(native.XorRva),
                decoded_sha256 = Hash(decoded),
            });
        }
        if (matched.Count != Encrypted.Length)
            throw new InvalidDataException("Native and structural decoders disagree on which metadata tables are encrypted.");
        return evidence.ToArray();
    }

    private static byte[] Reconstruct(byte[] raw, Section[] sections, byte[][] clear, int headerLength, int version)
    {
        var shift = HeaderSize - headerLength;
        var output = new byte[sections.Max(section => section.Start + section.Size) + shift];
        Put(output, 0, Magic);
        Put(output, 4, (uint)version);
        for (var index = 0; index < sections.Length; index++)
        {
            var section = sections[index];
            var start = section.Start + shift;
            var at = 8 + index * 12;
            Put(output, at, (uint)start);
            Put(output, at + 4, (uint)section.Size);
            Put(output, at + 8, (uint)section.Count);
            ReadOnlySpan<byte> table = clear[index] is { } decoded ? decoded : raw.AsSpan(section.Start, section.Size);
            table.CopyTo(output.AsSpan(start));
        }
        return output;
    }

    private static uint U32(ReadOnlySpan<byte> bytes, int offset) => BinaryPrimitives.ReadUInt32LittleEndian(bytes[offset..]);
    private static void Put(Span<byte> bytes, int offset, uint value) => BinaryPrimitives.WriteUInt32LittleEndian(bytes[offset..], value);
    private static string Hex(int value) => $"0x{value:x}";
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static void Xor(ReadOnlySpan<byte> input, Span<byte> output, int key)
    {
        for (var i = 0; i < input.Length; i++)
            output[i] = (byte)(input[i] ^ (byte)(key + i));
    }
}
