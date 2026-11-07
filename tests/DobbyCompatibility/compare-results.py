"""Report actual correctness failures separately from baseline regressions."""
import argparse,hashlib,json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
p=argparse.ArgumentParser()
p.add_argument('mode',choices=['snapshot','compare'])
p.add_argument('--runtime-root',type=Path,required=True)
p.add_argument('--build-root',type=Path,required=True)
a=p.parse_args()

def inventory(root):
 return {path.relative_to(root).as_posix():{'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
         for path in sorted(root.rglob('*')) if path.is_file()}

def load(relative):return json.loads((a.build_root/relative).read_text(encoding='utf-8-sig'))

if a.mode=='snapshot':
 (a.build_root/'runtime-input-inventory.json').write_text(json.dumps(inventory(a.runtime_root),indent=2)+'\n',encoding='utf-8')
 sys.exit(0)

native=load('native-results/results.json');managed=load('managed-results/results.json')
baseline=load('jcc-baseline.json');candidate=load('jcc-candidate.json')
original_inventory=load('runtime-input-inventory.json')
unchanged=original_inventory==inventory(a.runtime_root)
regressions=[];improvements=[];mismatches=[]
for group,report in [('native',native),('managed',managed)]:
 old_cases=report['libraries']['baseline']['cases'];new_cases=report['libraries']['candidate']['cases']
 if set(old_cases)!=set(new_cases):mismatches.append(group+': case inventory changed')
 for name,old in old_cases.items():
  new=new_cases[name]
  if old['passed'] and not new['passed']:regressions.append(group+': '+name)
  if not old['passed'] and new['passed']:improvements.append(group+': '+name)
  if not old['passed'] and not new['passed'] and old.get('error')!=new.get('error'):
   mismatches.append(group+': '+name+' failure changed')
  if old['passed'] and new['passed']:
   for key in ('checks','callbackCalls') if group=='native' else ('checks','callbacks','runtimeVersion','wrapper','appliedAfterDispose'):
    if old.get(key)!=new.get(key):mismatches.append(group+': '+name+' changed '+key)
failed={label:sorted(name for name,case in item['cases'].items() if not case['passed'])
        for label,item in native['libraries'].items()}
jcc=[]
for old,new in zip(baseline['cases'],candidate['cases'],strict=True):
 jcc.append({'fixture':old['fixture'],'baselineBranchTargetErrorBytes':old['branchTargetErrorBytes'],
             'candidateBranchTargetErrorBytes':new['branchTargetErrorBytes'],
             'rawGeneratedTrampolineBytesIdentical':old['trampolineBytes']==new['trampolineBytes'],
             'baselineNegativeResult':old['trampolineNegativeResult'],'candidateNegativeResult':new['trampolineNegativeResult']})
same_baseline_jcc=(failed.get('baseline')==['conditional','conditional-long']
                   and failed.get('candidate')==failed.get('baseline')
                   and all(x['baselineBranchTargetErrorBytes']==x['candidateBranchTargetErrorBytes']==4 for x in jcc))
all_correct=native['allPassed'] and managed['allPassed']
report={'noRegressionDetectedInExercisedCases':not regressions and not mismatches and unchanged,
 'allCorrectnessTestsPassed':all_correct,'allNativeCorrectnessTestsPassed':native['allPassed'],
 'nativeCasesPerLibrary':native['caseCountPerLibrary'],
 'nativePassedPerLibrary':{label:sum(case['passed'] for case in item['cases'].values()) for label,item in native['libraries'].items()},
 'nativeCorrectnessFailures':failed,'samePreExistingJccFailureObserved':same_baseline_jcc,
 'jccDiagnostics':jcc,'managedActualBepInExWrapperCasesPerLibrary':len(managed['libraries']['baseline']['cases']),
 'managedAllPassedOnBothLibraries':managed['allPassed'],
 'baselineSha256':native['libraries']['baseline']['sha256'],'candidateSha256':native['libraries']['candidate']['sha256'],
 'regressions':regressions,'improvements':improvements,'otherBehaviorMismatches':mismatches,
 'sourceRuntimeUnchanged':unchanged,'runtimeFilesCompared':len(original_inventory),
 'fixtureOnly':True,'gameLaunched':False,'osApiHooked':False,
 'knownFailureExplanation':'The pinned Dobby x64 relocator widens Jcc rel8 from two to six bytes without subtracting the four-byte instruction-length change. This candidate does not repair that existing bug.',
 'limit':'Synthetic baseline compatibility only; this does not establish universal instruction-relocator or game/plugin correctness.'}
(a.build_root/'comparison.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
# A baseline correctness failure remains a real nonzero test result.
sys.exit(0 if all_correct and report['noRegressionDetectedInExercisedCases'] else 1)
