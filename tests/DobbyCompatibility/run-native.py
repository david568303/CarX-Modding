"""Separate disposable children per case and per Dobby library, fixture-only hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
parser=argparse.ArgumentParser()
parser.add_argument('--baseline',type=Path,required=True)
parser.add_argument('--candidate',type=Path)
parser.add_argument('--build-root',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
assert not args.output_dir.exists(),'Fresh output directory required'
args.output_dir.mkdir(parents=True)
cases=['exports','rip-load','rip-lea','relative-call','conditional','conditional-long','integer','double','combined','near-enabled','near-disabled','cycles','parallel']
report={'fixtureOnly':True,'gameLaunched':False,'osApiHooked':False,'libraries':{}}
for label,dll in [('baseline',args.baseline),('candidate',args.candidate)]:
 if dll is None:continue
 result={'path':str(dll.resolve()),'sha256':hashlib.sha256(dll.read_bytes()).hexdigest(),'cases':{}}
 for case in cases:
  try:
   p=subprocess.run([str((args.build_root/'native-host.exe').resolve()),case,str(dll.resolve()),str((args.build_root/'fixture.dll').resolve())],cwd=args.output_dir,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
   (args.output_dir/f'{label}-{case}.stdout.txt').write_text(p.stdout,encoding='utf-8')
   (args.output_dir/f'{label}-{case}.stderr.txt').write_text(p.stderr,encoding='utf-8')
   lines=[line[7:] for line in p.stdout.splitlines() if line.startswith('RESULT ')]
   record=json.loads(lines[-1]) if lines else {'passed':False,'error':'No structured result; child may have aborted or crashed'}
   record['exitCode']=p.returncode
   record['observations']=[json.loads(line[12:]) for line in p.stdout.splitlines() if line.startswith('OBSERVATION ')]
   record['passed']=record.get('passed',False) and p.returncode==0
  except subprocess.TimeoutExpired:
   record={'passed':False,'error':'Child timed out'}
  result['cases'][case]=record
  print(label,case,record['passed'],flush=True)
 result['allPassed']=all(r['passed'] for r in result['cases'].values())
 report['libraries'][label]=result
report['allPassed']=all(r['allPassed'] for r in report['libraries'].values())
report['caseCountPerLibrary']=len(cases)
(args.output_dir/'results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
sys.exit(0 if report['allPassed'] else 1)
