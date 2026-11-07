"""Inspect generated branches in a disposable process; test-owned DLL only."""
import argparse,ctypes,json,sys
from pathlib import Path
import capstone
sys.dont_write_bytecode=True
p=argparse.ArgumentParser()
p.add_argument('--library',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
ctypes.windll.kernel32.SetErrorMode(3)
lib=ctypes.CDLL(str(a.library.resolve()));fixture=ctypes.CDLL(str(a.fixture.resolve()))
prepare=lib.DobbyPrepare;prepare.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)];prepare.restype=ctypes.c_int
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);md.detail=True
records=[]
for name in ('FixtureConditional','FixtureConditionalLong'):
 target=ctypes.cast(getattr(fixture,name),ctypes.c_void_p).value
 replacement=ctypes.cast(fixture.FixtureRipLoad,ctypes.c_void_p).value
 original=ctypes.string_at(target,64)
 before=list(md.disasm(original,target))
 expected_branch=next(i for i in before if i.mnemonic=='jl')
 trampoline=ctypes.c_void_p()
 status=prepare(target,replacement,ctypes.byref(trampoline));assert status==0 and trampoline.value
 generated=ctypes.string_at(trampoline.value,64)
 after=list(md.disasm(generated,trampoline.value))
 actual_branch=next(i for i in after if i.mnemonic=='jl')
 assert ctypes.string_at(target,64)==original
 F2=ctypes.CFUNCTYPE(ctypes.c_longlong,ctypes.c_longlong,ctypes.c_longlong)
 assert F2(target)(-3,7)==10
 wrong=F2(trampoline.value)(-3,7)
 delta=actual_branch.operands[0].imm-expected_branch.operands[0].imm
 record={'fixture':name,'targetAddress':hex(target),'trampolineAddress':hex(trampoline.value),
  'originalBranch':{'address':hex(expected_branch.address),'bytes':bytes(expected_branch.bytes).hex(),'length':expected_branch.size,'target':hex(expected_branch.operands[0].imm)},
  'relocatedBranch':{'address':hex(actual_branch.address),'bytes':bytes(actual_branch.bytes).hex(),'length':actual_branch.size,'target':hex(actual_branch.operands[0].imm)},
  'branchTargetErrorBytes':delta,'unhookedNegativeResult':10,'trampolineNegativeResult':wrong,
  'prepareStatus':status,'entryBytesUnchanged':True,'originalBytes':original.hex(),'trampolineBytes':generated.hex(),
  'decodedTrampoline':[{'address':hex(i.address),'mnemonic':i.mnemonic,'operands':i.op_str} for i in after[:12]]}
 records.append(record)
report={'library':str(a.library.resolve()),'sameExistingRel8ToRel32OffByFour':all(r['branchTargetErrorBytes']==4 for r in records),'fixtureOnly':True,'commitCalled':False,'cases':records,
 'sourceExplanation':'Pinned X64InstructionRelocation.cc widens Jcc rel8 from2 to6bytes but writes curr_orig_ip + orig_offset - curr_relo_ip; the four-byte instruction-length correction is missing.'}
a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
