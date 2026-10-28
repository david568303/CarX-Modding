"""Find Unity's native API binding calls without symbols or a reference build.

This module establishes which GameAssembly export is assigned to each loader
slot and preserves the loader's declaration order. It deliberately does not
assign canonical IL2CPP names: a separate schema/semantic validator must do that
before a runtime alias map is emitted.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_JUMP
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP, X86_REG_RAX, X86_REG_RDX


class DiscoveryError(ValueError):
    """The paired images did not establish a unique API binder."""


class NativeImage:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.pe = pefile.PE(str(path), fast_load=True)
        if self.pe.FILE_HEADER.Machine != 0x8664:
            raise DiscoveryError("Only x64 PE images are supported")
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.size = self.pe.OPTIONAL_HEADER.SizeOfImage
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        directory = self.pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXCEPTION']]
        if not directory.VirtualAddress or directory.Size < 12:
            raise DiscoveryError("The image has no native x64 unwind directory")
        raw = self.pe.get_data(directory.VirtualAddress, directory.Size)
        self.records = {}
        for offset in range(0, len(raw) - 11, 12):
            begin, end, unwind = struct.unpack_from('<III', raw, offset)
            if begin and begin < end <= self.size:
                self.records[begin] = (begin, end, unwind)
        self.starts = sorted(self.records)
        self.groups = {}
        self.roots = {}
        for begin in self.starts:
            root = self.unwind_root(begin)
            self.roots[begin] = root
            self.groups.setdefault(root, []).append(self.records[begin])
        self.instruction_cache = {}
        self.imports = {}
        self.pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        for descriptor in getattr(self.pe, 'DIRECTORY_ENTRY_IMPORT', []):
            for symbol in descriptor.imports:
                if symbol.name:
                    self.imports[symbol.address - self.base] = symbol.name.decode('ascii')

    def unwind_root(self, begin: int, seen=None) -> int:
        seen = set() if seen is None else seen
        if begin in seen or len(seen) >= 32:
            raise DiscoveryError("Cyclic or excessively deep unwind chaining")
        seen.add(begin)
        record = self.records.get(begin)
        if record is None:
            raise DiscoveryError("A chained unwind function has no runtime entry")
        info = self.pe.get_data(record[2], 4)
        if len(info) != 4:
            raise DiscoveryError("Truncated native unwind header")
        if not (info[0] >> 3) & 4:
            return begin
        tail = 4 + ((info[2] + 1) // 2) * 4
        raw = self.pe.get_data(record[2] + tail, 12)
        if len(raw) != 12:
            raise DiscoveryError("Truncated chained unwind entry")
        parent_begin, parent_end, _ = struct.unpack('<III', raw)
        parent = self.records.get(parent_begin)
        if parent is None or parent[1] != parent_end:
            raise DiscoveryError("Unwind chaining does not match the runtime directory")
        return self.unwind_root(parent_begin, seen)

    def function_root(self, rva: int):
        position = bisect.bisect_right(self.starts, rva) - 1
        if position < 0:
            return None
        begin = self.starts[position]
        return self.roots[begin] if rva < self.records[begin][1] else None

    def instructions(self, root: int):
        if root in self.instruction_cache:
            return self.instruction_cache[root]
        ranges = self.groups.get(root)
        instructions = []
        if ranges:
            for begin, end, _ in sorted(ranges):
                instructions.extend(self.md.disasm(self.pe.get_data(begin, end - begin), self.base + begin))
        else:
            # Ordinary import tail thunks and leaf helpers can lack unwind data.
            for ins in self.md.disasm(self.pe.get_data(root, 256), self.base + root):
                instructions.append(ins)
                if ins.mnemonic in ('ret', 'int3', 'jmp'):
                    break
        self.instruction_cache[root] = instructions
        return instructions

    def writable_slot(self, rva: int):
        section = self.pe.get_section_by_rva(rva)
        return rva % 8 == 0 and section is not None and bool(section.Characteristics & 0x80000000)


def read_c_string(image: NativeImage, rva: int, maximum: int = 256):
    if not 0 <= rva < image.size:
        return None
    raw = image.pe.get_data(rva, maximum)
    terminator = raw.find(b'\0')
    if terminator <= 0:
        return None
    try:
        return raw[:terminator].decode('ascii')
    except UnicodeDecodeError:
        return None


def export_inventory(path: Path):
    with pefile.PE(str(path), fast_load=True) as game:
        if game.FILE_HEADER.Machine != 0x8664:
            raise DiscoveryError("GameAssembly is not x64")
        game.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
        directory = game.OPTIONAL_HEADER.DATA_DIRECTORY[0]
        exports = {}
        export_directory = getattr(game, 'DIRECTORY_ENTRY_EXPORT', None)
        if export_directory is None:
            raise DiscoveryError("GameAssembly has no export directory")
        for symbol in export_directory.symbols:
            if symbol.name is None:
                continue
            try:
                name = symbol.name.decode('ascii')
            except UnicodeDecodeError:
                continue
            section = game.get_section_by_rva(symbol.address)
            if (symbol.forwarder or section is None or not section.Characteristics & 0x20000000
                    or directory.VirtualAddress <= symbol.address < directory.VirtualAddress + directory.Size):
                continue
            exports[name] = symbol.address
        if len(exports) < 20:
            raise DiscoveryError("Too few local executable GameAssembly exports")
        return exports


def candidate_functions(image: NativeImage, exports: dict):
    """Locate alias-name address loads; disassembly later confirms boundaries."""
    groups = {}
    for section in image.pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        data = section.get_data()
        # Windows x64's second pointer argument is RDX. This is an instruction
        # recognizer, not a captured game signature; every relative target must
        # independently name an actual export of the paired native runtime.
        for match in re.finditer(rb'\x48\x8d\x15....', data, flags=re.DOTALL):
            load_rva = section.VirtualAddress + match.start()
            string_rva = load_rva + 7 + struct.unpack_from('<i', match.group(), 3)[0]
            name = read_c_string(image, string_rva)
            if name not in exports:
                continue
            root = image.function_root(load_rva)
            if root is not None:
                groups.setdefault(root, set()).add(load_rva)
    return groups


def extract_function_bindings(image: NativeImage, root: int, exports: dict):
    instructions = image.instructions(root)
    bindings, rejected = [], []
    for index, ins in enumerate(instructions):
        if ins.mnemonic != 'lea' or len(ins.operands) != 2:
            continue
        destination, source = ins.operands
        if (destination.type != X86_OP_REG or destination.reg != X86_REG_RDX
                or source.type != X86_OP_MEM or source.mem.base != X86_REG_RIP):
            continue
        name_rva = ins.address + ins.size + source.mem.disp - image.base
        name = read_c_string(image, name_rva)
        if name not in exports:
            continue
        call_index = None
        for current in range(index + 1, min(index + 9, len(instructions))):
            following = instructions[current]
            if following.mnemonic == 'call':
                call_index = current
                break
            if following.mnemonic == 'ret' or following.group(CS_GRP_JUMP):
                break
            _, writes = following.regs_access()
            if X86_REG_RDX in writes:
                break
        if call_index is None or call_index + 2 >= len(instructions):
            rejected.append({'actual': name, 'load_rva': hex(ins.address-image.base), 'reason': 'no unambiguous export lookup call'})
            continue
        call = instructions[call_index]
        store = instructions[call_index + 1]
        test = instructions[call_index + 2]
        if (store.mnemonic != 'mov' or len(store.operands) != 2
                or store.operands[0].type != X86_OP_MEM or store.operands[0].mem.base != X86_REG_RIP
                or store.operands[0].size != 8 or store.operands[1].type != X86_OP_REG or store.operands[1].reg != X86_REG_RAX):
            rejected.append({'actual': name, 'reason': 'lookup result is not immediately stored in an API pointer slot'})
            continue
        if (test.mnemonic != 'test' or len(test.operands) != 2
                or any(op.type != X86_OP_REG or op.reg != X86_REG_RAX for op in test.operands)):
            rejected.append({'actual': name, 'reason': 'lookup result does not have the required missing-export check'})
            continue
        slot_rva = store.address + store.size + store.operands[0].mem.disp - image.base
        if not image.writable_slot(slot_rva):
            rejected.append({'actual': name, 'reason': 'API pointer slot is not aligned writable image data'})
            continue
        operand = call.operands[0]
        if operand.type == X86_OP_IMM:
            call_target = {'kind': 'direct', 'rva': operand.imm-image.base}
        elif operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
            call_target = {'kind': 'indirect', 'rva': call.address+call.size+operand.mem.disp-image.base}
        else:
            rejected.append({'actual': name, 'reason': 'export resolver call target cannot be established'})
            continue
        bindings.append(dict(actual=name, export_rva=hex(exports[name]), slot_rva=hex(slot_rva),
                             string_rva=hex(name_rva), load_rva=hex(ins.address-image.base),
                             call_rva=hex(call.address-image.base), store_rva=hex(store.address-image.base),
                             call_target=call_target))
    return bindings, rejected


def resolver_import_witness(image: NativeImage, target: dict):
    """Require the shared resolver's local call graph to reach GetProcAddress."""
    if target['kind'] == 'indirect':
        if image.imports.get(target['rva']) == 'GetProcAddress':
            return {'import_rva': hex(target['rva']), 'functions': []}
        raise DiscoveryError("The binder's indirect resolver is not GetProcAddress")
    pending = [(target['rva'], [])]
    seen = set()
    while pending:
        rva, path = pending.pop(0)
        root = image.function_root(rva)
        root = rva if root is None else root
        if root in seen:
            continue
        seen.add(root)
        if len(seen) > 512 or len(path) >= 7:
            continue
        current_path = path + [hex(root)]
        for ins in image.instructions(root):
            if ins.mnemonic not in ('call', 'jmp') or not ins.operands:
                continue
            operand = ins.operands[0]
            if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
                imported_rva = ins.address + ins.size + operand.mem.disp - image.base
                if image.imports.get(imported_rva) == 'GetProcAddress':
                    return dict(import_rva=hex(imported_rva), call_rva=hex(ins.address-image.base), functions=current_path)
            elif operand.type == X86_OP_IMM:
                child = operand.imm-image.base
                if 0 <= child < image.size:
                    pending.append((child, current_path))
    raise DiscoveryError("The shared native API resolver could not be connected to GetProcAddress")


def discover_bindings(unity_path: Path, game_path: Path):
    unity_path, game_path = Path(unity_path), Path(game_path)
    image = NativeImage(unity_path)
    try:
        return _discover_loaded_image(image, unity_path, game_path)
    finally:
        image.pe.close()


def _discover_loaded_image(image: NativeImage, unity_path: Path, game_path: Path):
    exports = export_inventory(game_path)
    candidates = candidate_functions(image, exports)
    results = []
    for root, references in candidates.items():
        if len(references) < 20:
            continue
        bindings, rejected = extract_function_bindings(image, root, exports)
        if len(bindings) < 20:
            continue
        if rejected:
            raise DiscoveryError(f"A candidate API binder has unvalidated export references: {rejected[:3]}")
        targets = {(entry['call_target']['kind'], entry['call_target']['rva']) for entry in bindings}
        if len(targets) != 1:
            raise DiscoveryError("The API binder uses inconsistent native export resolvers")
        if len({entry['slot_rva'] for entry in bindings}) != len(bindings) or len({entry['actual'] for entry in bindings}) != len(bindings):
            raise DiscoveryError("The API binder has duplicate pointer slots or export names")
        witness = resolver_import_witness(image, bindings[0]['call_target'])
        results.append((root, bindings, witness))
    if len(results) != 1:
        raise DiscoveryError(f"Expected exactly one complete native API binder, found {len(results)}")
    root, bindings, import_witness = results[0]
    ranges = sorted(image.groups[root])
    for index, entry in enumerate(bindings):
        entry['index'] = index
    return dict(format=1, method='native-unwind-and-export-binding-dataflow',
                unity_player=str(unity_path.resolve()), game_assembly=str(game_path.resolve()),
                unity_player_sha256=hashlib.sha256(unity_path.read_bytes()).hexdigest(),
                game_assembly_sha256=hashlib.sha256(game_path.read_bytes()).hexdigest(),
                loader=dict(rva=hex(root), length=sum(end-begin for begin,end,_ in ranges),
                            ranges=[dict(begin=hex(begin), end=hex(end)) for begin,end,_ in ranges]),
                binding_count=len(bindings), bindings=bindings, resolver_import_witness=import_witness,
                rejected=[], pdb_used=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unity', type=Path, required=True)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = discover_bindings(args.unity, args.game)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'binding_count': result['binding_count'], 'loader': result['loader'],
                      'resolver_import_witness': result['resolver_import_witness'], 'pdb_used': False}))


if __name__ == '__main__':
    main()
