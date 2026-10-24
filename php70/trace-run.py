#!/usr/bin/env python3
"""Build test-only instrumented legacy/hardened source copies and observe ordering."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2]/'php-src')
 p.add_argument('--ref',default='HEAD')
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--image',default='php70-security-toolchain:latest')
 p.add_argument('--jobs',type=int,default=4)
 a=p.parse_args()
 if a.jobs<1: p.error('--jobs must be positive')
 source=a.source.resolve()
 if subprocess.check_output(['git','-C',str(source),'status','--porcelain']).strip(): p.error('Commit intended source changes first')
 revision=subprocess.check_output(['git','-C',str(source),'rev-parse',a.ref+'^{commit}'],text=True).strip()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 harness=out/'harness';shutil.copytree(Path(__file__).resolve().parent/'harness',harness)
 # Only this trace-specific snapshot applies instrumentation; normal builds remain unchanged.
 build=harness/'build.sh';s=build.read_text();anchor='cd /work/source\n'
 if s.count(anchor)!=1: raise RuntimeError('build anchor mismatch')
 build.write_text(s.replace(anchor,'python3 /harness/instrument-session.py /work/source\n'+anchor,1))
 report={'report_mode':'instrumented','core_source_instrumented':True,'pass':False,'completed':False,'test_only_instrumented_build':True,'source_commit':revision,
         'modes':{},'limits':['Linux NTS FPM; tested callbacks and session consumers only. Third-party callbacks not loaded.',
         'Observer uses stack formatting and OS append writes; instrumentation may change timing. Original uninstrumented gates remain separate.',
         'This run closes the pre-RINIT session consumer evidence gap for these requests, not all CVE/OOM lifecycle coverage.'],
         'harness_sha256':{str(f.relative_to(harness)):hashlib.sha256(f.read_bytes()).hexdigest() for f in harness.rglob('*') if f.is_file()}}
 def execute(command,log):
  with log.open('wb') as stream: subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
 try:
  archive=out/'source.tar'
  execute(['git','-C',str(source),'archive','--format=tar','--output='+str(archive),revision],out/'archive.log')
  report['source_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
  report['image_id']=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',a.image],text=True).strip()
  for mode,buildmode in (('legacy','legacy'),('hardened','debug')):
   folder=out/mode;folder.mkdir();report['modes'][mode]={'pass':False}
   command=['docker','run','--rm','--network','none','--security-opt=no-new-privileges',
    '-e','BUILD_JOBS='+str(a.jobs),'-e','PYTHONOPTIMIZE=',
    '-v',str(archive)+':/input/source.tar:ro','-v',str(harness)+':/harness:ro',
    '-v',str(folder)+':/work','--entrypoint','sh',report['image_id']]
   print('Building test-only instrumented '+mode,flush=True)
   execute(command+['/harness/build.sh',buildmode],folder/'build.log')
   execute(command+['-ec','python3 /harness/trace-invariants.py --fpm /work/install/sbin/php-fpm --output /work/trace.json'+(' --legacy' if mode=='legacy' else '')],folder/'trace-run.log')
   data=json.loads((folder/'trace.json').read_text())
   if not data.get('pass') or not data.get('completed'): raise RuntimeError('Incomplete trace '+mode)
   execute(command+['-ec','python3 /harness/fpm-invariants.py --fpm /work/install/sbin/php-fpm --output /work/fpm.json'+(' --expect-baseline' if mode=='legacy' else '')],folder/'fpm-run.log')
   regression=json.loads((folder/'fpm.json').read_text())
   if not regression.get('pass') or not regression.get('completed'): raise RuntimeError('Incomplete regression '+mode)
   report['modes'][mode]={'pass':True,'trace':data,'regression':regression}
  report['pre_rinit_consumer_difference_observed']=True
  report['pass']=True;report['completed']=True
 except (Exception,KeyboardInterrupt) as error:
  report['error']=type(error).__name__+': '+str(error)
  print(report['error'],file=sys.stderr)
 finally:
  (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if report['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
