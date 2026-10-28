"""Infer metadata decoder parameters from native IL2CPP initialization code.

Inputs are a GameAssembly PE, its verified binary-derived API map and
metadata. No game version, native RVA, metadata field offset, or XOR key is
embedded. Instruction shapes are checked and ambiguous cases are rejected.
"""
from __future__ import annotations
import argparse,bisect,configparser,hashlib,json,struct
from pathlib import Path
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_REG,X86_OP_MEM,X86_OP_IMM,X86_REG_RIP


def full(reg:str)->str:
    if not reg:return ''
    if reg in ('eax','ax','al','ah'):return 'rax'
    if reg in ('ecx','cx','cl','ch'):return 'rcx'
    if reg in ('edx','dx','dl','dh'):return 'rdx'
    if reg in ('ebx','bx','bl','bh'):return 'rbx'
    if reg.startswith('e') and reg[1:] in ('si','di','sp','bp'):return 'r'+reg[1:]
    return reg.rstrip('dwb') if reg.startswith('r') and len(reg)>2 and reg[1].isdigit() else reg


class Image:
    def __init__(self,path):
        self.path=Path(path);self.pe=pefile.PE(str(path),fast_load=True);self.base=self.pe.OPTIONAL_HEADER.ImageBase
        if self.pe.FILE_HEADER.Machine != 0x8664:
            raise ValueError('Native metadata inference currently supports x64 PE images')
        self.md=Cs(CS_ARCH_X86,CS_MODE_64);self.md.detail=True
        self.pe.parse_data_directories(directories=[0])
        self.exports={s.name.decode():s.address for s in self.pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
        pdata=next(s.get_data() for s in self.pe.sections if s.Name.startswith(b'.pdata'))
        records=[struct.unpack_from('<III',pdata,i) for i in range(0,len(pdata)-11,12)]
        self.records={a:(a,b,u) for a,b,u in records if a and b>a};self.groups={};self.to_root={}
        for a,b,u in self.records.values():
            root=self.unwind_root(a);self.to_root[a]=root;self.groups.setdefault(root,[]).append((a,b,u))
        self.starts=sorted(self.records);self.cache={}
    def unwind_root(self,a,depth=0):
        if depth>20:raise ValueError('Cyclic native unwind chaining')
        q=self.records.get(a)
        if not q:return a
        data=self.pe.get_data(q[2],4);flags=data[0]>>3
        if not flags&4:return a
        tail=4+((data[2]+1)//2)*4
        begin,end,info=struct.unpack('<III',self.pe.get_data(q[2]+tail,12))
        return self.unwind_root(begin,depth+1)
    def function(self,rva):
        root=self.to_root.get(rva,rva)
        if root in self.cache:return self.cache[root]
        if root in self.groups:
            ins=[]
            for a,b,u in sorted(self.groups[root]):ins.extend(self.md.disasm(self.pe.get_data(a,b-a),self.base+a))
        else:
            # Leaf API wrappers have no unwind record. Stop at their tail jump.
            ins=[]
            for i in self.md.disasm(self.pe.get_data(root,256),self.base+root):
                ins.append(i)
                if i.mnemonic in ('ret','int3','jmp'):break
        self.cache[root]=ins;return ins
    def reg(self,op):return full(self.md.reg_name(op.reg)) if op.type==X86_OP_REG else None
    def memreg(self,mem,which='base'):return full(self.md.reg_name(getattr(mem,which)))
    def direct_calls(self,ins):
        return [i.operands[0].imm-self.base for i in ins if i.mnemonic in ('call','jmp') and i.operands and i.operands[0].type==X86_OP_IMM and 0<=i.operands[0].imm-self.base<self.pe.OPTIONAL_HEADER.SizeOfImage]


def header_loops(image,ins):
    result=[]
    for k,i in enumerate(ins):
        if i.mnemonic!='xor' or len(i.operands)!=2 or i.operands[0].type!=X86_OP_MEM or i.operands[0].size!=1 or image.reg(i.operands[1])!='rax':continue
        compare=next((x for x in ins[k+1:k+6] if x.mnemonic=='cmp' and x.operands[0].type==X86_OP_REG and x.operands[1].type==X86_OP_IMM and 128<=x.operands[1].imm<=8192),None)
        if not compare:continue
        index=image.reg(compare.operands[0]);length=compare.operands[1].imm
        lea=next((x for x in reversed(ins[max(0,k-4):k]) if x.mnemonic=='lea' and image.reg(x.operands[0])=='rax' and x.operands[1].type==X86_OP_MEM and image.memreg(x.operands[1].mem)==index and not x.operands[1].mem.index),None)
        if not lea:continue
        allocations=[]
        for n,x in enumerate(ins[:k]):
            if x.mnemonic!='call' or x.operands[0].type!=X86_OP_IMM:continue
            setup=next((p for p in reversed(ins[max(0,n-5):n]) if p.mnemonic=='mov' and image.reg(p.operands[0])=='rcx' and p.operands[1].type==X86_OP_IMM and p.operands[1].imm==length),None)
            if setup:allocations.append((n,x))
        if len(allocations)!=1:continue
        mem=i.operands[0].mem;regs={image.memreg(mem),image.memreg(mem,'index')}
        if index not in regs:continue
        regs.remove(index)
        if len(regs)!=1:continue
        result.append(dict(length=length,key=lea.operands[1].mem.disp&255,index_reg=index,header_reg=regs.pop(),allocation_index=allocations[0][0],allocator=allocations[0][1].operands[0].imm-image.base,loop_index=k,loop_rva=hex(i.address-image.base)))
    return result


def extract_sections(image,ins,header):
    alloc=header['allocator'];allocations=[k for k,i in enumerate(ins) if k>header['loop_index'] and i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM and i.operands[0].imm-image.base==alloc]
    sections=[]
    for at,next_at in zip(allocations,allocations[1:]+[len(ins)]):
        load=next((x for x in reversed(ins[max(0,at-5):at]) if x.mnemonic in ('mov','movsxd') and image.reg(x.operands[0])=='rcx' and x.operands[1].type==X86_OP_MEM and x.operands[1].size==4 and x.operands[1].mem.base!=X86_REG_RIP),None)
        if not load:continue
        size_field=load.operands[1].mem.disp;span=ins[at+1:next_at]
        copy_at=next((k for k,i in enumerate(span) if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM),None)
        if copy_at is None:continue
        setup=span[:copy_at];copy=span[copy_at]
        offset_load=next((i for i in setup if i.mnemonic=='mov' and image.reg(i.operands[0])=='rcx' and i.operands[1].type==X86_OP_MEM and i.operands[1].size==4 and i.operands[1].mem.base!=X86_REG_RIP),None)
        size_load=next((i for i in setup if i.mnemonic=='movsxd' and image.reg(i.operands[0])=='r8' and i.operands[1].type==X86_OP_MEM and i.operands[1].mem.disp==size_field),None)
        if not offset_load or not size_load:continue
        offset_field=offset_load.operands[1].mem.disp;delta=0
        for i in setup:
            if i.mnemonic in ('add','sub') and image.reg(i.operands[0])=='rcx' and i.operands[1].type==X86_OP_IMM:delta+=(1 if i.mnemonic=='add' else -1)*i.operands[1].imm
        xor_at=next((k for k,i in enumerate(span[copy_at+1:],copy_at+1) if i.mnemonic=='xor' and i.operands[0].type==X86_OP_MEM and i.operands[0].size==1 and image.reg(i.operands[1])=='rax'),None)
        if xor_at is None:continue
        expression=None
        for i in span[max(copy_at+1,xor_at-8):xor_at]:
            if not i.operands:continue
            if i.mnemonic=='lea' and image.reg(i.operands[0])=='rax' and i.operands[1].type==X86_OP_MEM:
                m=i.operands[1].mem
                if image.memreg(m)=='rcx' and not m.index:expression=[1,0,m.disp]
            elif i.mnemonic=='movzx' and image.reg(i.operands[0])=='rax' and image.reg(i.operands[1])=='rcx':expression=[1,0,0]
            elif i.mnemonic in ('add','sub') and image.reg(i.operands[0])=='rax' and expression is not None:
                sign=1 if i.mnemonic=='add' else -1;src=i.operands[1]
                if src.type==X86_OP_IMM:expression[2]+=sign*src.imm
                elif src.type==X86_OP_MEM and src.size==1 and src.mem.disp==size_field:expression[1]+=sign
                else:expression=None
        if expression is None:raise ValueError(f'Unknown section XOR arithmetic at {span[xor_at].address-image.base:x}')
        globals_stored=[i.address+i.size+i.operands[0].mem.disp-image.base for i in setup if i.mnemonic=='mov' and i.operands[0].type==X86_OP_MEM and i.operands[0].mem.base==X86_REG_RIP and image.reg(i.operands[1])=='rax']
        sections.append(dict(size_field=size_field,offset_field=offset_field,offset_adjustment=delta,xor_index_coefficient=expression[0],xor_size_coefficient=expression[1],xor_constant=expression[2],allocation_rva=hex(ins[at].address-image.base),copy_rva=hex(copy.address-image.base),copy_function_rva=hex(copy.operands[0].imm-image.base),xor_rva=hex(span[xor_at].address-image.base),runtime_pointer_globals=[hex(x) for x in globals_stored]))
    return sections


def discover(image,start):
    visited=set();queue=[(start,0,[])];candidates=[]
    while queue:
        rva,depth,path=queue.pop(0);root=image.to_root.get(rva,rva)
        if root in visited:continue
        visited.add(root)
        if len(visited)>10000:raise ValueError('Native callgraph exceeds diagnostic bound')
        ins=image.function(root)
        loops=header_loops(image,ins)
        for header in loops:
            sections=extract_sections(image,ins,header)
            if len(sections)>=3:candidates.append(dict(function_rva=hex(root),call_path=[hex(x) for x in path+[root]],header=header,sections=sections))
        if depth<3:
            queue.extend((target,depth+1,path+[root]) for target in image.direct_calls(ins) if target not in visited)
    if len(candidates)!=1:raise ValueError(f'Expected one unambiguous metadata decoder; found {len(candidates)} among {len(visited)} native functions')
    return candidates[0],len(visited)


def _validated_init_rva_contents(image: Image, api_map_path: Path, actual_hash: str) -> int:
    """Accept the generated INI, or an identity-bound JSON diagnostic report."""
    if api_map_path.suffix.lower()=='.json':
        api=json.loads(api_map_path.read_text(encoding='utf-8-sig'))
        if api['game_assembly_sha256'].lower()!=actual_hash:
            raise ValueError('API map does not match GameAssembly SHA256')
        alias=api['mapping']['il2cpp_init']
        start=image.exports.get(alias)
        witness=next((item for item in api['witnesses'] if item['canonical']=='il2cpp_init'),None)
        if start is None or witness is None or witness['actual']!=alias or int(witness['export_rva'],16)!=start:
            raise ValueError('Init API witness does not match the native export')
    else:
        ini=configparser.ConfigParser(interpolation=None)
        ini.optionxform=str
        with api_map_path.open(encoding='utf-8-sig') as stream:ini.read_file(stream)
        if (int(ini['Target']['TimeDateStamp'],16)!=image.pe.FILE_HEADER.TimeDateStamp or
                int(ini['Target']['SizeOfImage'],16)!=image.pe.OPTIONAL_HEADER.SizeOfImage):
            raise ValueError('API map target identity does not match GameAssembly')
        value=ini['Exports']['il2cpp_init'].split(',')
        if len(value)!=2:raise ValueError('Malformed il2cpp_init API binding')
        alias,expected=value
        start=image.exports.get(alias)
        if start is None or int(expected,16)!=start:
            raise ValueError('Init API alias/RVA does not match GameAssembly export')
    section=image.pe.get_section_by_rva(start)
    directory=image.pe.OPTIONAL_HEADER.DATA_DIRECTORY[0]
    if (section is None or not section.Characteristics&0x20000000 or
            directory.VirtualAddress<=start<directory.VirtualAddress+directory.Size):
        raise ValueError('Init API is not executable local native code')
    return start


def _validated_init_rva(image: Image, api_map_path: Path, actual_hash: str) -> int:
    try:
        return _validated_init_rva_contents(image, api_map_path, actual_hash)
    except (KeyError, IndexError, TypeError, configparser.Error) as error:
        raise ValueError(f'Malformed API map {api_map_path.name}: {error}') from error


def infer_decoder(game_path: Path | str, api_map_path: Path | str='doorstop_api.ini') -> dict:
    """Infer header/section transforms using the game's verified init API.

    The returned dictionary contains only JSON-compatible values. Its section
    fields identify native header locations and affine byte XOR expressions;
    they do not assign canonical metadata section names.
    """
    game_path=Path(game_path);api_map_path=Path(api_map_path)
    with game_path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    image=Image(game_path)
    try:
        start=_validated_init_rva(image,api_map_path,actual)
        result,visited=discover(image,start)
        result['format']=1
        result['method']='verified-init-callgraph-and-native-decoder-dataflow'
        result['game_assembly_sha256']=actual
        result['native_functions_examined']=visited
        return result
    finally:image.pe.close()


def decode_header(metadata: bytes, inference: dict) -> bytes:
    """Apply the inferred native header transform without mutating input."""
    header=inference['header']
    if len(metadata)<header['length']:raise ValueError('Metadata is shorter than the inferred native header')
    return bytes(value^((index+header['key'])&255) for index,value in enumerate(metadata[:header['length']]))


def resolve_section_ranges(metadata: bytes, inference: dict) -> list[dict]:
    """Validate and annotate inferred sections with metadata file ranges."""
    header=decode_header(metadata,inference)
    result=[]
    for index,section in enumerate(inference['sections']):
        size=struct.unpack_from('<I',header,section['size_field'])[0]
        offset=struct.unpack_from('<I',header,section['offset_field'])[0]+section['offset_adjustment']
        if offset<inference['header']['length'] or offset+size>len(metadata):
            raise ValueError(f'Inferred section {index} lies outside metadata: {offset:x}+{size:x}')
        result.append(dict(section,file_offset=offset,byte_size=size))
    ranges=sorted((item['file_offset'],item['file_offset']+item['byte_size']) for item in result if item['byte_size'])
    if any(first[1]>second[0] for first,second in zip(ranges,ranges[1:])):
        raise ValueError('Inferred eager metadata sections overlap')
    return result


def decode_eager_sections(metadata: bytes, inference: dict) -> list[dict]:
    """Return inferred section descriptors plus their decoded ``data`` bytes."""
    result=[]
    for section in resolve_section_ranges(metadata,inference):
        size=section['byte_size'];offset=section['file_offset']
        data=bytes(value^((index*section['xor_index_coefficient']+size*section['xor_size_coefficient']+section['xor_constant'])&255)
                   for index,value in enumerate(metadata[offset:offset+size]))
        result.append(dict(section,data=data,decoded_sha256=hashlib.sha256(data).hexdigest()))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--api-map',type=Path,default=Path('doorstop_api.ini'))
    parser.add_argument('--output',type=Path,help='Optional inference JSON output')
    parser.add_argument('--metadata',type=Path,help='Optional metadata to validate and decode')
    parser.add_argument('--decoded-dir',type=Path,help='Optional directory for decoded header and eager sections')
    args=parser.parse_args()
    if args.decoded_dir and not args.metadata:parser.error('--decoded-dir requires --metadata')
    result=infer_decoder(args.game,args.api_map)
    if args.metadata:
        raw=args.metadata.read_bytes();sections=decode_eager_sections(raw,result)
        result['sections']=[{key:value for key,value in section.items() if key!='data'} for section in sections]
        if args.decoded_dir:
            args.decoded_dir.mkdir(parents=True,exist_ok=True)
            (args.decoded_dir/'decoded-header.bin').write_bytes(decode_header(raw,result))
            for index,section in enumerate(sections):(args.decoded_dir/f'section-{index:02d}.bin').write_bytes(section['data'])
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    header=result['header']
    print(f"Inferred header length0x{header['length']:x}, XOR key0x{header['key']:x}, {len(result['sections'])} eager sections; examined {result['native_functions_examined']} native functions")
    if args.output:print(args.output.resolve())

if __name__=='__main__':main()
