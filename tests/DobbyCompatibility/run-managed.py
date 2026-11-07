"""Actual shipped BepInEx wrapper, exact existing isolated CoreCLR 6.0.7 host."""
import argparse,json,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
p=argparse.ArgumentParser()
for name in ('baseline','candidate','core','fixture','app','dotnet','output-dir'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();assert not a.output_dir.exists();a.output_dir.mkdir(parents=True)
result={'libraries':{},'gameLaunched':False,'fixtureOnly':True}
for label,dll in [('baseline',a.baseline),('candidate',a.candidate)]:
 cases={}
 for case in ('direct','relative-thunk','indirect-thunk','invoke-four'):
  work=a.output_dir/(label+'-'+case);work.mkdir()
  output=work/'result.json'
  command=[str(a.dotnet.resolve()),str(a.app.resolve()),str(a.core.resolve()),str(dll.resolve()),str(a.fixture.resolve()),case,str(output.resolve())]
  try:
   proc=subprocess.run(command,cwd=work,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60)
   (work/'stdout.txt').write_text(proc.stdout,encoding='utf-8');(work/'stderr.txt').write_text(proc.stderr,encoding='utf-8')
   record=json.loads(output.read_text()) if output.exists() else {'passed':False,'error':'No managed result; child aborted or crashed'}
   record['exitCode']=proc.returncode;record['passed']=record.get('passed',False) and proc.returncode==0
  except subprocess.TimeoutExpired:record={'passed':False,'error':'Managed child timed out'}
  cases[case]=record;print(label,case,record['passed'],flush=True)
 result['libraries'][label]={'cases':cases,'allPassed':all(c['passed'] for c in cases.values())}
result['allPassed']=all(x['allPassed'] for x in result['libraries'].values())
(a.output_dir/'results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));sys.exit(0 if result['allPassed'] else 1)
