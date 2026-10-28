"""Assign IL2CPP API identities using an independent ABI and native semantics.

The schema contains only public API declarations from a Unity-generated SDK;
it contains no game aliases, addresses, image identifiers, or symbol data.
Declaration order alone is insufficient: distributed native semantic anchors
must agree before a runtime alias map can be produced.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP, X86_REG_RCX

from discover_api_bindings import NativeImage, export_inventory


class SchemaError(ValueError):
    pass


SCHEMA_PATH = Path(__file__).with_name('il2cpp-api-schema.json')


def load_schema(path=SCHEMA_PATH):
    schema = json.loads(Path(path).read_text(encoding='utf-8'))
    functions = schema.get('functions', [])
    names = [item.get('name') for item in functions]
    if schema.get('format') != 1 or len(names) < 100 or len(names) != len(set(names)):
        raise SchemaError('The independent API declaration schema is invalid')
    if any(item.get('guard') not in (None, 'IL2CPP_ENABLE_PROFILER') for item in functions):
        raise SchemaError('The API schema has an unsupported compile-time condition')
    return schema


def schema_profiles(schema):
    """Compiler feature profiles, not a list of supported game versions."""
    for profiler in (False, True):
        functions = [item for item in schema['functions']
                     if item['guard'] is None or profiler]
        yield {'IL2CPP_ENABLE_PROFILER': profiler}, functions


class SemanticImage:
    def __init__(self, path, mapping):
        self.image = NativeImage(Path(path))
        self.exports = export_inventory(Path(path))
        self.mapping = mapping
        self.checks = []

    def body(self, api):
        name = api if api.startswith('il2cpp_') else 'il2cpp_' + api
        if name not in self.mapping or self.mapping[name] not in self.exports:
            raise SchemaError(f'Missing native anchor API: {name}')
        return self.follow(self.exports[self.mapping[name]])

    def follow(self, rva):
        seen = set()
        for _ in range(12):
            if rva in seen or not 0 <= rva < self.image.size:
                raise SchemaError('Invalid native API tail-call chain')
            seen.add(rva)
            ins = [item for item in self.image.instructions(rva)
                   if item.mnemonic not in ('nop', 'endbr64')]
            if len(ins) == 1 and ins[0].mnemonic == 'jmp' and ins[0].operands[0].type == X86_OP_IMM:
                rva = ins[0].operands[0].imm - self.image.base
                continue
            if not ins:
                raise SchemaError('Native API body is empty')
            return rva, ins
        raise SchemaError('Native API tail-call chain is too deep')

    def record(self, names, check, **evidence):
        if isinstance(names, str):
            names = [names]
        self.checks.append({'apis': [n if n.startswith('il2cpp_') else 'il2cpp_' + n for n in names],
                            'check': check, **evidence})

    def member(self, api, size, *, offset=None, address=False):
        rva, ins = self.body(api)
        if len(ins) != 2 or ins[-1].mnemonic != 'ret':
            raise SchemaError(f'{api} is not a pure native member accessor')
        value = ins[0]
        allowed = ('lea',) if address else ('mov', 'movzx', 'movsx', 'movsxd')
        if value.mnemonic not in allowed or len(value.operands) != 2:
            raise SchemaError(f'{api} does not have the expected accessor operation')
        destination, source = value.operands
        if (destination.type != X86_OP_REG or self.image.md.reg_name(destination.reg) not in ('rax', 'eax')
                or source.type != X86_OP_MEM or source.mem.base != X86_REG_RCX
                or source.mem.index or (not address and source.size != size)
                or (offset is not None and source.mem.disp != offset)):
            raise SchemaError(f'{api} does not match its standard native member contract')
        displacement = source.mem.disp
        if not 0 <= displacement <= 4096:
            raise SchemaError(f'{api} has an implausible native member displacement')
        self.record(api, 'pure-member-address' if address else 'pure-member-load',
                    body_rva=hex(rva), displacement=displacement, width=size)
        return displacement

    def bit(self, api, *, shift, offset=None, width=None):
        rva, ins = self.body(api)
        if len(ins) != 4 or ins[-1].mnemonic != 'ret':
            raise SchemaError(f'{api} is not a pure native flag accessor')
        load, move, mask, _ = ins
        if load.mnemonic not in ('mov', 'movzx') or len(load.operands) != 2:
            raise SchemaError(f'{api} has no flag load')
        source = load.operands[1]
        if (source.type != X86_OP_MEM or source.mem.base != X86_REG_RCX or source.mem.index
                or (offset is not None and source.mem.disp != offset)
                or (width is not None and source.size != width)
                or move.mnemonic not in ('shr', 'sar') or move.operands[1].type != X86_OP_IMM
                or move.operands[1].imm != shift or mask.mnemonic != 'and'
                or mask.operands[1].type != X86_OP_IMM or mask.operands[1].imm != 1):
            raise SchemaError(f'{api} does not extract its documented flag bit')
        self.record(api, 'native-flag-bit', body_rva=hex(rva), displacement=source.mem.disp,
                    width=source.size, shift=shift)
        return source.mem.disp

    def global_access(self, api, write=False, size=8):
        rva, ins = self.body(api)
        if len(ins) != 2 or ins[-1].mnemonic != 'ret' or ins[0].mnemonic != 'mov':
            raise SchemaError(f'{api} is not a pure global accessor')
        destination, source = ins[0].operands
        memory = destination if write else source
        register = source if write else destination
        if (memory.type != X86_OP_MEM or memory.mem.base != X86_REG_RIP or memory.mem.index
                or memory.size != size or register.type != X86_OP_REG
                or self.image.md.reg_name(register.reg) != ('rcx' if write else 'rax')):
            raise SchemaError(f'{api} does not match its native global contract')
        cell = ins[0].address + ins[0].size + memory.mem.disp - self.image.base
        section = self.image.pe.get_section_by_rva(cell)
        if section is None or not section.Characteristics & 0x80000000:
            raise SchemaError(f'{api} does not access writable runtime state')
        return cell

    def direct_calls(self, ins):
        return [item.operands[0].imm - self.image.base for item in ins
                if item.mnemonic in ('call', 'jmp') and item.operands
                and item.operands[0].type == X86_OP_IMM]


def validate_getter_anchors(game, mapping):
    image = SemanticImage(game, mapping)
    try:
        return _validate_getter_anchors(image)
    finally:
        image.image.pe.close()


def _validate_getter_anchors(image):
    # Stable Windows-x64 native object/string/array headers, expressed in pointer
    # units. These are IL2CPP ABI facts, not offsets in a particular game image.
    pointer = 8
    image.member('object_get_class', pointer, offset=0)
    image.member('assembly_get_image', pointer, offset=0)
    image.member('object_unbox', pointer, offset=2 * pointer, address=True)
    image.member('array_length', 4, offset=3 * pointer)
    image.member('string_length', 4, offset=2 * pointer)
    image.member('string_chars', pointer, offset=2 * pointer + 4, address=True)

    # FieldInfo and PropertyInfo prefixes are independently described C structs.
    for name, offset, size in (
        ('field_get_name', 0, pointer), ('field_get_type', pointer, pointer),
        ('field_get_parent', 2 * pointer, pointer), ('field_get_offset', 3 * pointer, 4),
        ('property_get_parent', 0, pointer), ('property_get_name', pointer, pointer),
        ('property_get_get_method', 2 * pointer, pointer), ('property_get_set_method', 3 * pointer, pointer),
        ('class_get_name', 2 * pointer, pointer), ('class_get_namespace', 3 * pointer, pointer),
        ('image_get_name', 0, pointer), ('image_get_filename', 0, pointer),
        ('image_get_assembly', 2 * pointer, pointer),
    ):
        image.member(name, size, offset=offset)

    # MethodInfo has acquired optional leading pointers across Unity ABIs. Infer
    # the name location, then check adjacent members rather than fixing its RVA
    # or even its struct prefix length.
    name_offset = image.member('method_get_name', pointer)
    if name_offset % pointer or not 2 * pointer <= name_offset <= 8 * pointer:
        raise SchemaError('MethodInfo name prefix is not a recognized native pointer layout')
    image.member('method_get_declaring_type', pointer, offset=name_offset + pointer)
    image.member('method_get_class', pointer, offset=name_offset + pointer)
    image.member('method_get_return_type', pointer, offset=name_offset + 2 * pointer)
    token_offset = image.member('method_get_token', 4)
    parameter_count = image.member('method_get_param_count', 1)
    if parameter_count != token_offset + 4 + 2 + 2 + 2:
        raise SchemaError('MethodInfo token/flags/slot/parameter-count layout does not agree')

    # il2cpp_method_get_flags optionally writes implementation flags and returns
    # method flags. Both native getters must refer to the inferred token prefix.
    _, flags_body = image.body('method_get_flags')
    offsets = []
    for target in image.direct_calls(flags_body):
        _, getter = image.follow(target)
        if len(getter) == 2 and getter[-1].mnemonic == 'ret' and getter[0].mnemonic == 'movzx':
            src = getter[0].operands[1]
            if src.type == X86_OP_MEM and src.mem.base == X86_REG_RCX and not src.mem.index and src.size == 2:
                offsets.append(src.mem.disp)
    if token_offset + 4 not in offsets or token_offset + 6 not in offsets:
        raise SchemaError('Method flag and implementation-flag getters do not agree with MethodInfo')
    image.record('method_get_flags', 'method-flags-follow-token', token_displacement=token_offset,
                 getter_displacements=offsets)

    type_attrs = image.member('type_get_attrs', 2)
    type_kind = image.member('type_get_type', 1, offset=type_attrs + 2)
    image.bit('type_is_byref', shift=29, offset=type_attrs, width=4)
    image.bit('type_is_static', shift=4, offset=type_attrs, width=4)
    rva, pointer_body = image.body('type_is_pointer_type')
    if (len(pointer_body) != 3 or pointer_body[0].mnemonic != 'cmp'
            or pointer_body[1].mnemonic != 'sete' or pointer_body[-1].mnemonic != 'ret'):
        raise SchemaError('Pointer-type test is not a native comparison')
    source, constant = pointer_body[0].operands
    if (source.type != X86_OP_MEM or source.mem.base != X86_REG_RCX or source.mem.index
            or source.mem.disp != type_kind or source.size != 1
            or constant.type != X86_OP_IMM or constant.imm != 0x0F):
        raise SchemaError('Pointer-type test does not compare IL2CPP_TYPE_PTR')
    image.record('type_is_pointer_type', 'native-type-enum-comparison', body_rva=hex(rva), type_value=0x0F)

    class_flags = image.member('class_get_flags', 4)
    image.bit('class_is_abstract', shift=7, offset=class_flags, width=4)
    generic_flags = image.bit('class_is_generic', shift=4, width=1)
    image.bit('class_is_enum', shift=2, offset=generic_flags, width=1)
    image.member('class_get_rank', 1)
    image.member('class_get_static_field_data', pointer)

    # The image class-count wrapper may simply load the count or zero-extend a
    # call to the shared native 32-bit member getter.
    rva, count_body = image.body('image_get_class_count')
    if len(count_body) == 2:
        image.member('image_get_class_count', 4, offset=3 * pointer)
    else:
        targets = image.direct_calls(count_body)
        if len(targets) != 1:
            raise SchemaError('Image class-count wrapper has an unexpected call graph')
        _, getter = image.follow(targets[0])
        if len(getter) != 2 or getter[-1].mnemonic != 'ret' or getter[0].mnemonic != 'mov':
            raise SchemaError('Image class count is not a native integer member getter')
        member = getter[0].operands[1]
        if member.type != X86_OP_MEM or member.mem.base != X86_REG_RCX or member.mem.index or member.mem.disp != 3 * pointer or member.size != 4:
            raise SchemaError('Image class-count member does not match the image prefix')
        image.record('image_get_class_count', 'zero-extended-member-count', body_rva=hex(rva))

    # GC controls provide anchors in the largest interval between struct getters.
    read = image.global_access('gc_get_max_time_slice_ns')
    write = image.global_access('gc_set_max_time_slice_ns', write=True)
    if read != write:
        raise SchemaError('GC time-slice getter/setter do not address the same native state')
    image.record(['gc_get_max_time_slice_ns', 'gc_set_max_time_slice_ns'],
                 'shared-gc-time-slice-state', state_rva=hex(read))
    counters = []
    for name, operation in (('gc_disable', 'inc'), ('gc_enable', 'dec')):
        _, body = image.body(name)
        cells = set()
        for ins in body:
            if ins.mnemonic != operation or not ins.operands:
                continue
            op = ins.operands[0]
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP and not op.mem.index:
                cells.add(ins.address + ins.size + op.mem.disp - image.image.base)
        if len(cells) != 1:
            raise SchemaError(f'{name} has no unique native GC suppression counter')
        counters.append(cells.pop())
    if counters[0] != counters[1]:
        raise SchemaError('GC enable/disable controls do not share a counter')
    image.record(['gc_disable', 'gc_enable'], 'balanced-gc-suppression-counter', state_rva=hex(counters[0]))

    # These API functions report the object/array ABI directly. They agree with
    # the accessor contracts checked above, independently of game-image layout.
    for name, expected in (
        ('object_header_size', 2 * pointer), ('array_object_header_size', 4 * pointer),
        ('offset_of_array_length_in_array_object_header', 3 * pointer),
        ('offset_of_array_bounds_in_array_object_header', 2 * pointer),
    ):
        rva, body = image.body(name)
        if (len(body) != 2 or body[-1].mnemonic != 'ret' or body[0].mnemonic != 'mov'
                or body[0].operands[1].type != X86_OP_IMM or body[0].operands[1].imm != expected):
            raise SchemaError(f'{name} disagrees with the declared native object ABI')
        image.record(name, 'self-reported-native-object-layout', body_rva=hex(rva), value=expected)

    heap_root, heap_body = image.body('gc_get_heap_size')
    _, used_body = image.body('gc_get_used_size')
    calls = image.direct_calls(used_body)
    if not calls or image.follow(calls[0])[0] != heap_root or not any(ins.mnemonic == 'sub' for ins in used_body):
        raise SchemaError('Used GC bytes do not derive from heap size minus free space')
    if not any(ins.mnemonic == 'sub' for ins in heap_body):
        raise SchemaError('The native GC heap-size computation is unrecognized')
    image.record(['gc_get_heap_size', 'gc_get_used_size'], 'used-bytes-derived-from-heap-and-free-space',
                 heap_function_rva=hex(heap_root))

    # On Windows the current-thread API retrieves its managed-thread pointer
    # through TLS. The debugger API separately uses the OS debugger query.
    for name, required in (('thread_current', 'TlsGetValue'), ('is_debugger_attached', 'IsDebuggerPresent')):
        rva, body = image.body(name)
        imports = []
        for ins in body:
            if ins.mnemonic not in ('call', 'jmp') or not ins.operands:
                continue
            op = ins.operands[0]
            if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                imports.append(image.image.imports.get(ins.address + ins.size + op.mem.disp - image.image.base))
        if required not in imports:
            raise SchemaError(f'{name} does not reach its expected Windows runtime operation')
        image.record(name, 'windows-runtime-import', body_rva=hex(rva), imported_function=required)

    # Shared attribute-data initialization links three different public API
    # contracts without relying on the implementation's private symbol name.
    attr_names = ('custom_attrs_get_attr', 'custom_attrs_has_attr', 'custom_attrs_construct')
    initializers = []
    for name in attr_names:
        _, body = image.body(name)
        calls = image.direct_calls(body)
        if not calls:
            raise SchemaError(f'{name} has no attribute-data initialization call')
        initializers.append(calls[0])
    if len(set(initializers)) != 1:
        raise SchemaError('Custom attribute APIs do not share their native data initializer')
    image.record(list(attr_names), 'shared-custom-attribute-data-initializer', target_rva=hex(initializers[0]))

    # GetComponent user-data optimization exposes its own offset contract.
    rva, offset_body = image.body('class_get_userdata_offset')
    if (len(offset_body) != 2 or offset_body[-1].mnemonic != 'ret'
            or offset_body[0].mnemonic != 'mov' or offset_body[0].operands[1].type != X86_OP_IMM):
        raise SchemaError('The class user-data offset API is not a constant offset')
    user_offset = offset_body[0].operands[1].imm
    _, setter = image.body('class_set_userdata')
    if len(setter) != 2 or setter[-1].mnemonic != 'ret' or setter[0].mnemonic != 'mov':
        raise SchemaError('The class user-data API is not a native pointer setter')
    dst, src = setter[0].operands
    if (dst.type != X86_OP_MEM or dst.mem.base != X86_REG_RCX or dst.mem.index
            or dst.mem.disp != user_offset or dst.size != pointer or src.type != X86_OP_REG
            or image.image.md.reg_name(src.reg) != 'rdx' or not pointer <= user_offset <= 4096):
        raise SchemaError('The class user-data setter disagrees with its offset API')
    image.record(['class_get_userdata_offset', 'class_set_userdata'], 'self-described-class-user-data-offset',
                 body_rva=hex(rva), displacement=user_offset)
    return image.checks


def canonicalize_bindings(unity_path, game_path, binding_discovery):
    unity_path, game_path = Path(unity_path), Path(game_path)
    for path, key in ((unity_path, 'unity_player_sha256'), (game_path, 'game_assembly_sha256')):
        if hashlib.sha256(path.read_bytes()).hexdigest() != binding_discovery.get(key):
            raise SchemaError('Native binding evidence does not match the supplied binary images')
    bindings = binding_discovery.get('bindings', [])
    if len(bindings) != binding_discovery.get('binding_count'):
        raise SchemaError('Native binding count is inconsistent')
    schema = load_schema()
    candidates = [(flags, functions) for flags, functions in schema_profiles(schema) if len(functions) == len(bindings)]
    if len(candidates) != 1:
        raise SchemaError('The native API binder does not match one unambiguous declared compiler-feature profile')
    flags, functions = candidates[0]
    inventory = export_inventory(game_path)
    mapping, witnesses = {}, []
    last_call = -1
    for index, (function, binding) in enumerate(zip(functions, bindings)):
        call = int(binding['call_rva'], 16)
        if binding.get('index') != index or call <= last_call:
            raise SchemaError('Native API bindings are not in validated loader declaration order')
        last_call = call
        alias = binding['actual']
        if alias not in inventory or inventory[alias] != int(binding['export_rva'], 16):
            raise SchemaError('A native binding export address is stale or inconsistent')
        mapping[function['name']] = alias
        witnesses.append(dict(binding, canonical=function['name'], prototype={
            'return_type': function['return_type'], 'parameters': function['parameters']},
            declaration_group=function['group']))
    if len(set(mapping.values())) != len(mapping):
        raise SchemaError('Canonical API bindings contain duplicate aliases')
    checks = validate_getter_anchors(game_path, mapping)
    from api_semantic_anchors import validate_critical_anchors
    for check in validate_critical_anchors(game_path, mapping):
        names = check.get('apis') or [check['api']]
        if check.get('api') == 'il2cpp_memory_pool_get_region_size':
            names = list(names) + ['il2cpp_memory_pool_set_region_size']
        checks.append(dict(check, apis=names))
    covered = {name for check in checks for name in check.get('apis', [])}
    gap = maximum_gap = 0
    for function in functions:
        if function['name'] in covered:
            maximum_gap = max(maximum_gap, gap)
            gap = 0
        else:
            gap += 1
    maximum_gap = max(maximum_gap, gap)
    if maximum_gap > 20:
        raise SchemaError('The API contract does not have sufficiently distributed semantic anchors')
    return {'mapping': mapping, 'witnesses': witnesses,
            'semantic_validation': {'passed': True, 'check_count': len(checks),
                'anchored_api_count': len(covered), 'maximum_unanchored_interval': maximum_gap,
                'anchored_apis': sorted(covered), 'checks': checks},
            'schema': {'contract': schema['contract'], 'compile_features': flags,
                'declaration_count': len(functions), 'sources': schema['sources'],
                'schema_sha256': hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest()},
            'mapping_count': len(mapping), 'canonical_slot_count': len(bindings),
            'unmapped': [], 'rejected': [], 'uses_symbols': False}
