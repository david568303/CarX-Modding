using System.Buffers.Binary;
using System.Globalization;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Text;
using Iced.Intel;

namespace BepInEx.MetadataBootstrap;

internal sealed record NativeHeader(int Length, int Key, int Direction, int LoopRva);
internal sealed record NativeSection(long SizeField, long OffsetField, long Adjustment, long SizeCoefficient,
    long Constant, int AllocationRva, int CopyRva, int XorRva);
internal sealed record NativeDecoder(NativeHeader Header, NativeSection[] Sections, int FunctionRva, int InitRva,
    int FunctionsExamined);

internal static class NativeMetadataDecoder
{
    private sealed record HeaderLoop(NativeHeader Header, int LoopIndex, int Allocator);
    private sealed record FunctionRange(int Start, int End, int UnwindRva);

    internal static NativeDecoder Infer(string gamePath, string mapPath)
    {
        using var image = new Image(gamePath);
        var start = image.ValidateInit(mapPath);
        var queue = new Queue<(int Rva, int Depth)>();
        var visited = new HashSet<int>();
        NativeDecoder? result = null;
        void Enqueue(int rva, int depth)
        {
            var root = image.FunctionRoot(rva);
            if (!visited.Add(root)) return;
            if (visited.Count > 10000)
                throw new InvalidDataException("Native metadata call graph exceeds its analysis bound.");
            queue.Enqueue((root, depth));
        }

        Enqueue(start, 0);
        while (queue.TryDequeue(out var next))
        {
            var instructions = image.DecodeFunction(next.Rva);
            foreach (var loop in FindHeaderLoops(image, instructions))
            {
                var sections = FindSections(image, instructions, loop);
                if (sections.Length < 3) continue;
                if (result is not null)
                    throw new InvalidDataException("Multiple native metadata decoders match the verified init call graph.");
                result = new NativeDecoder(loop.Header, sections, next.Rva, start, 0);
            }
            if (next.Depth == 3) continue;
            foreach (var instruction in instructions)
                if ((instruction.Mnemonic is Mnemonic.Call or Mnemonic.Jmp) && image.TryDirectTarget(instruction, out var target))
                    Enqueue(target, next.Depth + 1);
        }

        if (result is null)
            throw new InvalidDataException($"No native metadata decoder matched among {visited.Count} verified init call graph functions.");
        return result with { FunctionsExamined = visited.Count };
    }

    private static IEnumerable<HeaderLoop> FindHeaderLoops(Image image, List<Instruction> instructions)
    {
        for (var at = 0; at < instructions.Count; at++)
        {
            var xor = instructions[at];
            if (!IsByteXor(xor)) continue;
            var length = 0;
            var index = Register.None;
            for (var j = at + 1; j < Math.Min(instructions.Count, at + 6); j++)
            {
                var cmp = instructions[j];
                if (cmp.Mnemonic != Mnemonic.Cmp || cmp.Op0Kind != OpKind.Register
                    || !TryImmediate(cmp, out var value) || value is < 128 or > 8192) continue;
                length = (int)value;
                index = Destination(cmp);
                break;
            }
            if (length == 0 || (Base(xor) != index && Index(xor) != index) || Base(xor) == Index(xor))
                continue;

            (int Key, int Direction)? transform = null;
            for (var j = at - 1; j >= Math.Max(0, at - 4); j--)
            {
                var lea = instructions[j];
                if (lea.Mnemonic != Mnemonic.Lea || Destination(lea) != Register.RAX
                    || lea.Op1Kind != OpKind.Memory || Base(lea) != index || Index(lea) != Register.None) continue;
                transform = ((int)(Displacement(lea) & 255), 1);
                break;
            }
            if (transform is null && at >= 2)
            {
                // A descending stream materializes the key, then subtracts the loop index's low byte.
                var subtract = instructions[at - 1];
                var move = instructions[at - 2];
                if (subtract.Mnemonic == Mnemonic.Sub && subtract.Op0Register == Register.AL
                    && Source(subtract) == index && subtract.Op1Register is not (Register.AH or Register.BH or Register.CH or Register.DH)
                    && move.Mnemonic == Mnemonic.Mov
                    && move.Op0Register is Register.AL or Register.AX or Register.EAX or Register.RAX
                    && TryImmediate(move, out var key))
                    transform = ((int)(key & 255), -1);
            }
            if (transform is not { } header) continue;

            var allocations = new List<int>();
            for (var j = 0; j < at; j++)
            {
                var call = instructions[j];
                if (call.Mnemonic != Mnemonic.Call || !image.TryDirectTarget(call, out var target)) continue;
                for (var k = j - 1; k >= Math.Max(0, j - 5); k--)
                {
                    var setup = instructions[k];
                    if (setup.Mnemonic != Mnemonic.Mov || Destination(setup) != Register.RCX
                        || !TryImmediate(setup, out var argument) || argument != length) continue;
                    allocations.Add(target);
                    break;
                }
            }
            if (allocations.Count == 1)
                yield return new HeaderLoop(new NativeHeader(length, header.Key, header.Direction, image.Rva(xor.IP)), at, allocations[0]);
        }
    }

    private static NativeSection[] FindSections(Image image, List<Instruction> instructions, HeaderLoop header)
    {
        var allocations = new List<int>();
        for (var j = header.LoopIndex + 1; j < instructions.Count; j++)
        {
            var call = instructions[j];
            if (call.Mnemonic == Mnemonic.Call && image.TryDirectTarget(call, out var target) && target == header.Allocator)
                allocations.Add(j);
        }
        allocations.Add(instructions.Count);

        var sections = new List<NativeSection>();
        for (var allocation = 0; allocation < allocations.Count - 1; allocation++)
        {
            var at = allocations[allocation];
            var end = allocations[allocation + 1];
            long? sizeField = null;
            for (var j = at - 1; j >= Math.Max(0, at - 5); j--)
            {
                var load = instructions[j];
                if (!IsHeaderLoad(load)) continue;
                sizeField = Displacement(load);
                break;
            }
            if (sizeField is null) continue;

            var copy = at + 1;
            while (copy < end && (instructions[copy].Mnemonic != Mnemonic.Call
                || !image.TryDirectTarget(instructions[copy], out _))) copy++;
            if (copy == end) continue;

            long? offsetField = null;
            var readsCopySize = false;
            long adjustment = 0;
            for (var j = at + 1; j < copy; j++)
            {
                var setup = instructions[j];
                if (setup.Mnemonic == Mnemonic.Mov && IsHeaderLoad(setup))
                    offsetField ??= Displacement(setup);
                if (setup.Mnemonic == Mnemonic.Movsxd && Destination(setup) == Register.R8
                    && setup.Op1Kind == OpKind.Memory && Displacement(setup) == sizeField)
                    readsCopySize = true;
                if ((setup.Mnemonic is Mnemonic.Add or Mnemonic.Sub) && Destination(setup) == Register.RCX
                    && TryImmediate(setup, out var value))
                    adjustment += setup.Mnemonic == Mnemonic.Add ? value : -value;
            }
            if (offsetField is null || !readsCopySize) continue;

            var xor = copy + 1;
            while (xor < end && !IsByteXor(instructions[xor])) xor++;
            if (xor == end) continue;

            (long Size, long Constant)? expression = null;
            for (var j = Math.Max(copy + 1, xor - 8); j < xor; j++)
            {
                var setup = instructions[j];
                if (Destination(setup) != Register.RAX) continue;
                if (setup.Mnemonic == Mnemonic.Lea && setup.Op1Kind == OpKind.Memory
                    && Base(setup) == Register.RCX && Index(setup) == Register.None)
                    expression = (0, Displacement(setup));
                else if (setup.Mnemonic == Mnemonic.Movzx && Source(setup) == Register.RCX)
                    expression = (0, 0);
                else if ((setup.Mnemonic is Mnemonic.Add or Mnemonic.Sub) && expression is { } current)
                {
                    var sign = setup.Mnemonic == Mnemonic.Add ? 1 : -1;
                    if (TryImmediate(setup, out var value))
                        expression = (current.Size, current.Constant + sign * value);
                    else if (setup.Op1Kind == OpKind.Memory && setup.MemorySize.GetSize() == 1
                        && Displacement(setup) == sizeField)
                        expression = (current.Size + sign, current.Constant);
                    else
                        expression = null;
                }
            }
            if (expression is not { } resolved)
                throw new InvalidDataException($"Unknown section XOR expression at RVA 0x{image.Rva(instructions[xor].IP):x}.");
            sections.Add(new NativeSection(sizeField.Value, offsetField.Value, adjustment, resolved.Size,
                resolved.Constant, image.Rva(instructions[at].IP), image.Rva(instructions[copy].IP),
                image.Rva(instructions[xor].IP)));
        }
        return sections.ToArray();
    }

    private static bool IsHeaderLoad(Instruction i) => (i.Mnemonic is Mnemonic.Mov or Mnemonic.Movsxd)
        && Destination(i) == Register.RCX && i.Op1Kind == OpKind.Memory && i.MemorySize.GetSize() == 4
        && !i.IsIPRelativeMemoryOperand;

    private static bool IsByteXor(Instruction i) => i.Mnemonic == Mnemonic.Xor && i.Op0Kind == OpKind.Memory
        && i.MemorySize.GetSize() == 1 && Source(i) == Register.RAX;

    private static Register Destination(Instruction i) =>
        i.Op0Kind == OpKind.Register ? i.Op0Register.GetFullRegister() : Register.None;
    private static Register Source(Instruction i) =>
        i.Op1Kind == OpKind.Register ? i.Op1Register.GetFullRegister() : Register.None;
    private static Register Base(Instruction i) => i.MemoryBase.GetFullRegister();
    private static Register Index(Instruction i) => i.MemoryIndex.GetFullRegister();
    private static long Displacement(Instruction i) => unchecked((long)i.MemoryDisplacement64);

    private static bool TryImmediate(Instruction i, out long value)
    {
        value = 0;
        if (i.Op1Kind is not (OpKind.Immediate8 or OpKind.Immediate16 or OpKind.Immediate32 or OpKind.Immediate64
            or OpKind.Immediate8to16 or OpKind.Immediate8to32 or OpKind.Immediate8to64 or OpKind.Immediate32to64))
            return false;
        value = unchecked((long)i.GetImmediate(1));
        return true;
    }

    private sealed class Image : IDisposable
    {
        private const int MaxFunctionRange = 1024 * 1024;
        private readonly PEReader reader;
        private readonly PEHeader header;
        private readonly Dictionary<int, FunctionRange> ranges = new();
        private readonly Dictionary<int, int> roots = new();
        private readonly Dictionary<int, List<FunctionRange>> groups = new();
        private readonly Dictionary<int, BlobReader> unwindSections = new();

        internal Image(string path)
        {
            reader = new PEReader(File.OpenRead(path));
            try
            {
                header = reader.PEHeaders.PEHeader ?? throw new InvalidDataException("GameAssembly has no PE header.");
                if (header.Magic != PEMagic.PE32Plus || reader.PEHeaders.CoffHeader.Machine != Machine.Amd64)
                    throw new InvalidDataException("Native metadata inference requires an x64 GameAssembly.");
                var exception = header.ExceptionTableDirectory;
                if (exception.Size <= 0 || exception.Size % 12 != 0 || exception.Size > 16 * 1024 * 1024)
                    throw new InvalidDataException("GameAssembly has an invalid x64 exception table.");
                var data = Read(exception.RelativeVirtualAddress, exception.Size);
                for (var at = 0; at < data.Length; at += 12)
                {
                    var start = I32(data, at);
                    var end = I32(data, at + 4);
                    if (start != 0 && end > start)
                        ranges[start] = new FunctionRange(start, end, I32(data, at + 8));
                }
                foreach (var range in ranges.Values.OrderBy(range => range.Start))
                {
                    var root = UnwindRoot(range.Start);
                    roots.Add(range.Start, root);
                    if (!groups.TryGetValue(root, out var group))
                        groups.Add(root, group = new List<FunctionRange>());
                    group.Add(range);
                }
            }
            catch
            {
                reader.Dispose();
                throw;
            }
        }

        public void Dispose() => reader.Dispose();

        private int UnwindRoot(int rva)
        {
            for (var depth = 0; depth <= 20; depth++)
            {
                if (!ranges.TryGetValue(rva, out var range)) return rva;
                var info = ReadUnwind(range.UnwindRva, 4);
                if ((info.ReadByte() & (4 << 3)) == 0) return rva;
                info.ReadByte(); // Prologue length.
                var tail = 4 + (info.ReadByte() + 1) / 2 * 4;
                rva = ReadUnwind(checked(range.UnwindRva + tail), 12).ReadInt32();
            }
            throw new InvalidDataException("Native unwind chaining exceeds its depth bound.");
        }

        private BlobReader ReadUnwind(int rva, int length)
        {
            var index = reader.PEHeaders.GetContainingSectionIndex(rva);
            if (index < 0) throw new InvalidDataException($"Unwind data at RVA 0x{rva:x} has no PE section.");
            var start = reader.PEHeaders.SectionHeaders[index].VirtualAddress;
            // An image can contain hundreds of thousands of unwind records.
            // Keep views into PEReader-owned blocks rather than copying each tiny record.
            if (!unwindSections.TryGetValue(index, out var section))
                unwindSections.Add(index, section = reader.GetSectionData(start).GetReader());
            var offset = rva - start;
            if (offset < 0 || offset > section.Length - length)
                throw new InvalidDataException($"Unwind data at RVA 0x{rva:x} is not backed by the file.");
            section.Offset = offset;
            return section;
        }

        internal int FunctionRoot(int rva) => roots.GetValueOrDefault(rva, rva);
        internal int Rva(ulong address) => checked((int)(address - header.ImageBase));

        internal bool TryDirectTarget(Instruction instruction, out int target)
        {
            target = 0;
            if (instruction.Op0Kind != OpKind.NearBranch64 || instruction.NearBranchTarget < header.ImageBase)
                return false;
            var relative = instruction.NearBranchTarget - header.ImageBase;
            if (relative >= (ulong)header.SizeOfImage) return false;
            target = (int)relative;
            return true;
        }

        internal List<Instruction> DecodeFunction(int rva)
        {
            var instructions = new List<Instruction>();
            if (groups.TryGetValue(rva, out var group))
            {
                foreach (var range in group)
                    Decode(range.Start, range.End - range.Start, false, instructions);
            }
            else if (IsExecutable(rva))
                Decode(rva, Math.Min(256, reader.GetSectionData(rva).Length), true, instructions);
            return instructions;
        }

        private void Decode(int rva, int size, bool leaf, List<Instruction> instructions)
        {
            if (!IsExecutable(rva) || size <= 0 || size > MaxFunctionRange)
                throw new InvalidDataException($"Invalid native code range at RVA 0x{rva:x}.");
            var bytes = new ByteArrayCodeReader(Read(rva, size));
            var decoder = Iced.Intel.Decoder.Create(64, bytes);
            decoder.IP = header.ImageBase + (uint)rva;
            while (bytes.CanReadByte)
            {
                decoder.Decode(out var instruction);
                if (instruction.IsInvalid) break;
                instructions.Add(instruction);
                if (leaf && instruction.Mnemonic is Mnemonic.Ret or Mnemonic.Int3 or Mnemonic.Jmp) break;
            }
        }

        private bool IsExecutable(int rva)
        {
            var index = reader.PEHeaders.GetContainingSectionIndex(rva);
            return index >= 0 && (reader.PEHeaders.SectionHeaders[index].SectionCharacteristics & SectionCharacteristics.MemExecute) != 0;
        }

        private byte[] Read(int rva, int length)
        {
            if (rva <= 0 || length <= 0)
                throw new InvalidDataException("Invalid native image range.");
            var block = reader.GetSectionData(rva);
            if (length > block.Length)
                throw new InvalidDataException($"Native image range at RVA 0x{rva:x} is not backed by the file.");
            return block.GetContent(0, length).ToArray();
        }

        internal int ValidateInit(string mapPath)
        {
            var alias = "il2cpp_init";
            // Doorstop skips map generation when the canonical export already exists.
            // Prefer that exact local export even if an older install left a map behind.
            var canonical = FindExport(alias);
            if (canonical != 0) return RequireLocal(canonical);

            if (!File.Exists(mapPath))
                throw new InvalidDataException("An obfuscated GameAssembly requires the verified Doorstop API map.");
            var values = ReadIni(mapPath);
            var format = values.GetValueOrDefault("Target.Format");
            var discovery = values.GetValueOrDefault("Target.Discovery");
            if (format != "2" || discovery != "binary-loader-schema"
                || ParseHex(values.GetValueOrDefault("Target.TimeDateStamp")) != unchecked((uint)reader.PEHeaders.CoffHeader.TimeDateStamp)
                || ParseHex(values.GetValueOrDefault("Target.SizeOfImage")) != header.SizeOfImage)
                throw new InvalidDataException("Doorstop API map identity does not match GameAssembly.");
            var fields = values.GetValueOrDefault("Exports.il2cpp_init")?.Split(',', StringSplitOptions.TrimEntries);
            if (fields is not { Length: 2 } || fields[0].Length == 0)
                throw new InvalidDataException("Malformed il2cpp_init API binding.");
            var rva = FindExport(fields[0]);
            if (rva == 0 || ParseHex(fields[1]) != rva)
                throw new InvalidDataException("The verified init alias and RVA do not match the GameAssembly export.");
            return RequireLocal(rva);
        }

        private int RequireLocal(int rva)
        {
            var export = header.ExportTableDirectory;
            if (!IsExecutable(rva) || (rva >= export.RelativeVirtualAddress
                && rva - export.RelativeVirtualAddress < export.Size))
                throw new InvalidDataException("The verified init API does not point to local executable native code.");
            return rva;
        }

        private int FindExport(string name)
        {
            var directory = header.ExportTableDirectory;
            var table = Read(directory.RelativeVirtualAddress, 40);
            var functions = I32(table, 20);
            var names = I32(table, 24);
            if (functions is <= 0 or > 100000 || names is < 0 or > 100000)
                throw new InvalidDataException("Invalid GameAssembly export counts.");
            if (names == 0) return 0;
            var namePointers = Read(I32(table, 32), names * 4);
            var ordinals = Read(I32(table, 36), names * 2);
            var functionPointers = Read(I32(table, 28), functions * 4);
            for (var index = 0; index < names; index++)
            {
                var rva = I32(namePointers, index * 4);
                if (rva <= 0) throw new InvalidDataException("Invalid GameAssembly export name.");
                var block = reader.GetSectionData(rva);
                var text = block.GetContent(0, Math.Min(4096, block.Length)).AsSpan();
                var end = text.IndexOf((byte)0);
                if (end < 0) throw new InvalidDataException("Unterminated GameAssembly export name.");
                if (end != name.Length || Encoding.ASCII.GetString(text[..end]) != name) continue;
                var ordinal = BinaryPrimitives.ReadUInt16LittleEndian(ordinals.AsSpan(index * 2));
                if (ordinal >= functions) throw new InvalidDataException("Invalid GameAssembly export ordinal.");
                return I32(functionPointers, ordinal * 4);
            }
            return 0;
        }

        private static Dictionary<string, string> ReadIni(string path)
        {
            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var section = "";
            foreach (var raw in File.ReadLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] is '#' or ';') continue;
                if (line.StartsWith('[') && line.EndsWith(']'))
                {
                    section = line[1..^1];
                    continue;
                }
                var equal = line.IndexOf('=');
                if (equal <= 0 || !values.TryAdd(section + "." + line[..equal].Trim(), line[(equal + 1)..].Trim()))
                    throw new InvalidDataException("Malformed or duplicate entry in Doorstop API map.");
            }
            return values;
        }

        private static uint ParseHex(string? value)
        {
            if (value?.StartsWith("0x", StringComparison.OrdinalIgnoreCase) == true) value = value[2..];
            return uint.TryParse(value, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var number)
                ? number : throw new InvalidDataException("Missing or invalid hexadecimal value in Doorstop API map.");
        }

        private static int I32(byte[] bytes, int at) => BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(at));
    }
}
