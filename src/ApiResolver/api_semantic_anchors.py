"""Independent native IL2CPP ABI anchors for validating canonical API schemas.

Only instruction semantics and relationships within the supplied GameAssembly
are used. This file has no captured RVAs, randomized export names, debug-symbol
data, function byte signatures, or game-build checks.
"""
from __future__ import annotations

from pathlib import Path

from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

from discover_api_bindings import NativeImage, export_inventory


class SemanticAnchorError(ValueError):
    pass


def register_name(image, operand):
    if operand.type != X86_OP_REG:
        return None
    name = image.md.reg_name(operand.reg)
    if name in ('rax', 'eax', 'ax', 'al', 'ah'): return 'rax'
    if name in ('rcx', 'ecx', 'cx', 'cl', 'ch'): return 'rcx'
    if name in ('rdx', 'edx', 'dx', 'dl', 'dh'): return 'rdx'
    if name in ('rbx', 'ebx', 'bx', 'bl', 'bh'): return 'rbx'
    if name.startswith('e') and name[1:] in ('si', 'di', 'sp', 'bp'): return 'r' + name[1:]
    if name.startswith('r') and len(name) > 2 and name[1].isdigit(): return name.rstrip('dwb')
    return name


def memory_base(image, operand):
    if operand.type != X86_OP_MEM:
        return None
    name = image.md.reg_name(operand.mem.base)
    return name


def relative_cell(image, instruction, operand):
    if operand.type == X86_OP_MEM and operand.mem.base == X86_REG_RIP:
        return instruction.address + instruction.size + operand.mem.disp - image.base
    return None


def function_body(image, rva):
    """Follow ordinary export tail jumps without relying on wrapper addresses."""
    visited = set()
    while rva not in visited and len(visited) < 12:
        visited.add(rva)
        root = image.function_root(rva)
        root = rva if root is None else root
        instructions = image.instructions(root)
        significant = [ins for ins in instructions if ins.mnemonic not in ('nop', 'int3', 'endbr64')]
        if not significant:
            raise SemanticAnchorError('An expected API body contains no instructions')
        first = significant[0]
        if first.mnemonic == 'jmp' and first.operands and first.operands[0].type == X86_OP_IMM:
            rva = first.operands[0].imm - image.base
            if not 0 <= rva < image.size:
                raise SemanticAnchorError('An API export jumps outside its image')
            continue
        return root, significant
    raise SemanticAnchorError('Cyclic or excessively deep API export tail jumps')


def _direct_target(image, instruction):
    if instruction.mnemonic == 'call' and instruction.operands and instruction.operands[0].type == X86_OP_IMM:
        return instruction.operands[0].imm - image.base
    return None


def _locale_and_runtime(image, instructions):
    candidates = []
    for index, call in enumerate(instructions):
        target = _direct_target(image, call)
        if target is None:
            continue
        previous = instructions[max(0, index-5):index]
        category_zero = any(
            (ins.mnemonic == 'xor' and len(ins.operands) == 2
             and register_name(image, ins.operands[0]) == register_name(image, ins.operands[1]) == 'rcx')
            or (ins.mnemonic == 'mov' and len(ins.operands) == 2
                and register_name(image, ins.operands[0]) == 'rcx'
                and ins.operands[1].type == X86_OP_IMM and ins.operands[1].imm == 0)
            for ins in previous)
        empty_locale = []
        for ins in previous:
            if (ins.mnemonic != 'lea' or len(ins.operands) != 2
                    or register_name(image, ins.operands[0]) != 'rdx'):
                continue
            cell = relative_cell(image, ins, ins.operands[1])
            section = image.pe.get_section_by_rva(cell) if cell is not None else None
            if (section is not None and not section.Characteristics & 0x80000000
                    and image.pe.get_data(cell, 1) == b'\0'):
                empty_locale.append(cell)
        if not category_zero or len(empty_locale) != 1:
            continue
        following = next(((at, ins, _direct_target(image, ins))
                          for at, ins in enumerate(instructions[index+1:], index+1)
                          if _direct_target(image, ins) is not None), None)
        if following is None:
            continue
        at, invoke, runtime = following
        if at > index + 8:
            continue
        bool_return = any(ins.mnemonic == 'movzx' and len(ins.operands) == 2
                          and ins.operands[1].type == X86_OP_REG
                          and image.md.reg_name(ins.operands[1].reg) == 'al'
                          for ins in instructions[at+1:at+5])
        if bool_return:
            candidates.append(dict(locale_target=target, locale_string=empty_locale[0],
                                   locale_index=index, runtime_target=runtime, runtime_index=at,
                                   runtime_call=invoke.address-image.base))
    if len(candidates) != 1:
        raise SemanticAnchorError('Initialization did not establish one locale setup followed by a bool-returning Runtime::Init call')
    return candidates[0]


def _preserves_ascii_domain_argument(image, instructions, runtime_index):
    tags = {'rcx': 'domain'}
    for index, ins in enumerate(instructions[:runtime_index+1]):
        if index == runtime_index:
            return tags.get('rcx') == 'domain'
        if ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == X86_OP_REG:
            destination, source = register_name(image, ins.operands[0]), register_name(image, ins.operands[1])
            if source in tags: tags[destination] = tags[source]
            else: tags.pop(destination, None)
        elif ins.mnemonic in ('xor', 'lea') and ins.operands and ins.operands[0].type == X86_OP_REG:
            tags.pop(register_name(image, ins.operands[0]), None)
        elif ins.mnemonic == 'call':
            for name in ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11'):
                tags.pop(name, None)
    return False


def _global_getter(image, body):
    if len(body) != 2 or body[0].mnemonic != 'mov' or body[1].mnemonic != 'ret':
        return None
    move = body[0]
    if len(move.operands) != 2 or register_name(image, move.operands[0]) != 'rax' or move.operands[1].size != 8:
        return None
    cell = relative_cell(image, move, move.operands[1])
    return cell if cell is not None and image.writable_slot(cell) else None


def validate_critical_anchors(game_path: Path, mapping: dict[str, str]):
    image = NativeImage(Path(game_path))
    try:
        return _validate_loaded_anchors(image, game_path, mapping)
    finally:
        image.pe.close()


def _validate_loaded_anchors(image, game_path, mapping):
    exports = export_inventory(Path(game_path))
    required = ('il2cpp_init', 'il2cpp_init_utf16', 'il2cpp_domain_get', 'il2cpp_get_corlib',
                'il2cpp_memory_pool_get_region_size', 'il2cpp_memory_pool_set_region_size', 'il2cpp_runtime_invoke')
    missing = [name for name in required if name not in mapping or mapping[name] not in exports]
    if missing:
        raise SemanticAnchorError('Critical native API anchors are missing: ' + ', '.join(missing))
    bodies = {name: function_body(image, exports[mapping[name]]) for name in required}
    evidence = []

    ascii_root, ascii_body = bodies['il2cpp_init']
    utf_root, utf_body = bodies['il2cpp_init_utf16']
    ascii_init = _locale_and_runtime(image, ascii_body)
    utf_init = _locale_and_runtime(image, utf_body)
    if ascii_init['locale_target'] != utf_init['locale_target'] or ascii_init['runtime_target'] != utf_init['runtime_target']:
        raise SemanticAnchorError('ASCII and UTF16 initialization do not share their locale and runtime initialization functions')
    if not _preserves_ascii_domain_argument(image, ascii_body, ascii_init['runtime_index']):
        raise SemanticAnchorError('ASCII initialization does not forward its original domain-name argument')
    if not any(_direct_target(image, ins) is not None for ins in utf_body[:utf_init['locale_index']]):
        raise SemanticAnchorError('UTF16 initialization has no string conversion before shared initialization')
    evidence.append(dict(api='il2cpp_init', check='forwards-domain-through-locale-setup-to-bool-runtime-init',
                         function_rva=hex(ascii_root), runtime_init_rva=hex(ascii_init['runtime_target']), locale_function_rva=hex(ascii_init['locale_target'])))
    evidence.append(dict(api='il2cpp_init_utf16', check='converts-string-and-shares-ascii-runtime-init', function_rva=hex(utf_root)))

    getter_root, getter = bodies['il2cpp_memory_pool_get_region_size']
    setter_root, setter = bodies['il2cpp_memory_pool_set_region_size']
    pool_cell = _global_getter(image, getter)
    setter_cell = None
    if (len(setter) == 2 and setter[0].mnemonic == 'mov' and setter[1].mnemonic == 'ret'
            and len(setter[0].operands) == 2 and setter[0].operands[0].size == 8
            and register_name(image, setter[0].operands[1]) == 'rcx'):
        setter_cell = relative_cell(image, setter[0], setter[0].operands[0])
    if pool_cell is None or setter_cell != pool_cell:
        raise SemanticAnchorError('Memory-pool size setter/getter do not access the same writable native value')
    evidence.append(dict(api='il2cpp_memory_pool_get_region_size', check='paired-size-getter-setter-share-global',
                         getter_rva=hex(getter_root), setter_rva=hex(setter_root), global_rva=hex(pool_cell)))

    corlib_root, corlib_body = bodies['il2cpp_get_corlib']
    corlib_cell = _global_getter(image, corlib_body)
    if corlib_cell is None or corlib_cell == pool_cell:
        raise SemanticAnchorError('The corlib getter is not a distinct pointer singleton getter')
    runtime_root, runtime_body = function_body(image, ascii_init['runtime_target'])
    writes_corlib = any(ins.mnemonic == 'mov' and len(ins.operands) == 2
                        and relative_cell(image, ins, ins.operands[0]) == corlib_cell
                        for ins in runtime_body)
    if not writes_corlib:
        raise SemanticAnchorError('Runtime initialization does not initialize the corlib singleton returned by its API')
    evidence.append(dict(api='il2cpp_get_corlib', check='pointer-singleton-initialized-by-runtime-init',
                         function_rva=hex(corlib_root), global_rva=hex(corlib_cell), writer_rva=hex(runtime_root)))

    domain_root, domain_body = bodies['il2cpp_domain_get']
    global_loads, global_stores = [], []
    for ins in domain_body:
        if ins.mnemonic == 'mov' and len(ins.operands) == 2:
            destination, source = ins.operands
            cell = relative_cell(image, ins, source)
            if register_name(image, destination) == 'rax' and cell is not None:
                global_loads.append(cell)
            cell = relative_cell(image, ins, destination)
            if register_name(image, source) == 'rax' and cell is not None:
                global_stores.append(cell)
    shared = set(global_loads) & set(global_stores)
    guarded = any(ins.mnemonic == 'test' and len(ins.operands) == 2
                  and register_name(image, ins.operands[0]) == register_name(image, ins.operands[1]) == 'rax'
                  for ins in domain_body)
    if len(shared) == 1 and guarded:
        domain_cell = next(iter(shared))
        if not image.writable_slot(domain_cell) or global_loads[-1] != domain_cell:
            raise SemanticAnchorError('Domain singleton return does not match the initialized value')
        domain_kind = 'lazily-initialized-pointer-singleton'
    elif (len(domain_body) == 2 and domain_body[0].mnemonic == 'lea' and domain_body[1].mnemonic == 'ret'
          and register_name(image, domain_body[0].operands[0]) == 'rax'):
        domain_cell = relative_cell(image, domain_body[0], domain_body[0].operands[1])
        if domain_cell is None or not image.writable_slot(domain_cell):
            raise SemanticAnchorError('Static domain API does not return writable native singleton storage')
        domain_kind = 'static-domain-singleton-address'
    else:
        raise SemanticAnchorError('Domain getter does not match a supported native singleton implementation')
    if domain_cell in (pool_cell, corlib_cell):
        raise SemanticAnchorError('Domain, corlib, and allocator configuration globals are not distinct')
    evidence.append(dict(api='il2cpp_domain_get', check=domain_kind, function_rva=hex(domain_root), global_rva=hex(domain_cell)))

    invoke_root, invoke_body = bodies['il2cpp_runtime_invoke']
    clear_index = None
    for index, ins in enumerate(invoke_body):
        if (ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[0].type == X86_OP_MEM
                and memory_base(image, ins.operands[0]) == 'r9' and ins.operands[0].mem.disp == 0
                and ins.operands[0].size == 8 and ins.operands[1].type == X86_OP_IMM and ins.operands[1].imm == 0):
            clear_index = index
            break
    if clear_index is None:
        raise SemanticAnchorError('Runtime::Invoke does not clear its fourth exception-output argument')
    preceding = invoke_body[max(0, clear_index-5):clear_index]
    if not any(ins.mnemonic == 'test' and len(ins.operands) == 2
               and register_name(image, ins.operands[0]) == register_name(image, ins.operands[1]) == 'r9'
               for ins in preceding):
        raise SemanticAnchorError('Runtime::Invoke exception-output clear is not null-guarded')
    forward = False
    for index, ins in enumerate(invoke_body[clear_index+1:], clear_index+1):
        if _direct_target(image, ins) is None:
            continue
        before = invoke_body[max(clear_index+1,index-4):index]
        setup = {register_name(image, previous.operands[0])
                 for previous in before if previous.mnemonic == 'mov' and len(previous.operands) == 2
                 and previous.operands[0].type == X86_OP_REG and previous.operands[1].type == X86_OP_REG}
        if {'rcx','rdx','r8'} <= setup:
            forward = True
            break
    if not forward:
        raise SemanticAnchorError('Runtime::Invoke does not forward method, receiver, and argument pointers together')
    evidence.append(dict(api='il2cpp_runtime_invoke', check='four-pointer-ABI-null-guarded-exception-output-and-forwarding', function_rva=hex(invoke_root)))
    return evidence
